from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.kernel.models.policy import SystemPolicy
from app.kernel.models.registry import NodeRegistry


class PolicyResolver:
    @staticmethod
    async def get_policy(
        session: AsyncSession,
        policy_key: str,
        node_id: Optional[str] = None,
        item_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves a Configuration-as-Data policy using the documented 6-level fallback hierarchy
        (most-specific → least-specific):

          1. Specific node + specific item       (e.g., 'WH_KAMPALA' + 'PARAM-01')
          2. Specific node + any item             (e.g., 'WH_KAMPALA' + NULL)
          3. Node type + specific item            (e.g., 'type:MU' + 'PARAM-01')
          4. Node type + any item                 (e.g., 'type:MU' + NULL)
          5. Any node + commodity category         (e.g., NULL + 'category:DRUGS')
          6. Global                                (NULL + NULL)

        The first non-null match wins.

        The hierarchy is NOT "walk up the tree first, then check type." It is:
          - Check the specific node (level 1, 2)
          - Then check the node's TYPE (level 3, 4)
          - Then global/category (level 5, 6)
        Parent nodes are only consulted if the specific node has no match at levels 1-2
        AND the node type has no match at levels 3-4. Parent walk restarts the same
        level 1-2-3-4 sequence for the parent.
        """
        # Step 1: Fetch ALL rows for this policy_key in a single query
        stmt = select(SystemPolicy).where(SystemPolicy.policy_key == policy_key)
        all_policies = (await session.execute(stmt)).scalars().all()

        if not all_policies:
            return None

        # Build fast lookup: {(applies_to_node, applies_to_item): config}
        policy_dict = {
            (p.applies_to_node, p.applies_to_item): p.config for p in all_policies
        }

        # Step 2: Resolve node metadata and ancestry
        resolution_chain = []

        if node_id:
            current_uid = node_id
            max_depth = 10

            while current_uid and len(resolution_chain) < max_depth * 4:
                # Fetch the node record for type info
                node_stmt = select(NodeRegistry).where(
                    NodeRegistry.uid == current_uid,
                    NodeRegistry.valid_to.is_(None),
                )
                node_record = (await session.execute(node_stmt)).scalars().first()

                # Level 1: Specific node + specific item
                if item_id:
                    resolution_chain.append((current_uid, item_id))
                # Level 2: Specific node + NULL (any item)
                resolution_chain.append((current_uid, None))

                # Levels 3-4: Node type (only for the QUERIED node, not ancestors)
                # This ensures type-scoped policies are checked after the specific node
                # but before walking up to parent nodes.
                if current_uid == node_id and node_record and node_record.node_type:
                    node_type_prefixed = f"type:{node_record.node_type}"
                    if item_id:
                        resolution_chain.append((node_type_prefixed, item_id))
                    resolution_chain.append((node_type_prefixed, None))

                if not node_record or not node_record.parent_id:
                    break

                current_uid = node_record.parent_id

        # Level 5: NULL + specific item (before category and global)
        if item_id:
            resolution_chain.append((None, item_id))

        # Level 6: Global (NULL + NULL)
        resolution_chain.append((None, None))

        # Step 3: Walk the chain — first match wins
        for coord in resolution_chain:
            if coord in policy_dict:
                return policy_dict[coord]

        return None
