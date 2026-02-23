from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.kernel.models.policy import SystemPolicy
from app.kernel.models.registry import NodeRegistry

class PolicyResolver:
    
    @staticmethod
    async def get_policy(session: AsyncSession, policy_key: str, node_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a Configuration-as-Data policy using a Strict Fallback Hierarchy:
        1. Exact Match: Node + Item
        2. Semi-Match: Node + 'ALL' items
        3. Semi-Match: Parent Node + Item (Recursive up the tree)
        4. Semi-Match: Parent Node + 'ALL' items (Recursive up the tree)
        5. Global Default: 'GLOBAL' + 'ALL'
        
        Note: The `node_id` here should be the stable `uid`, not the surrogate row `id`.
        """
        
        # We need to traverse up the Node tree, so we fetch the ancestry path first.
        # Since NodeRegistry uses SCD Type 2, we fetch the *currently active* hierarchy
        # (Where valid_to is NULL).
        
        current_node_uid = node_id
        hierarchy_uids = []
        
        # Max depth safety valve to prevent infinite loops in bad data
        max_depth = 10 
        
        while current_node_uid and len(hierarchy_uids) < max_depth:
            hierarchy_uids.append(current_node_uid)
            
            stmt = select(NodeRegistry).where(
                NodeRegistry.uid == current_node_uid,
                NodeRegistry.valid_to.is_(None) # Get the currently active version
            )
            result = await session.execute(stmt)
            node_record = result.scalars().first()
            
            if node_record and node_record.parent_id:
                current_node_uid = node_record.parent_id
            else:
                break
                
        # Now we query the SystemPolicy table for all potentially matching combinations
        target_coords = []
        
        # Add all node-specific combinations
        for ancestor_uid in hierarchy_uids:
            target_coords.append((ancestor_uid, item_id))
            target_coords.append((ancestor_uid, "ALL"))
            
        # Add Global fallback
        target_coords.append(("GLOBAL", "ALL"))
        
        # Querying everything in one go for performance
        stmt = select(SystemPolicy).where(SystemPolicy.policy_key == policy_key)
        all_policies = (await session.execute(stmt)).scalars().all()
        
        if not all_policies:
            return None
            
        # Build a fast lookup dictionary: {(node, item): config}
        policy_dict = {(p.applies_to_node, p.applies_to_item): p.config for p in all_policies}
        
        # Evaluate Fallback Chain in exact order of precedence
        for coord in target_coords:
            if coord in policy_dict:
                return policy_dict[coord]
                
        return None
