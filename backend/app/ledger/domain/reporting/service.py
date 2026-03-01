from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.ledger.models.event_store import InventoryEvent, StockBalance
from app.ledger.schemas.reporting import LedgerHistoryResponse, StockBalanceResponse


class ReportingService:
    """
    The 'Query' side of CQRS.
    Responsible for fetching pre-calculated Read Models and strictly applying
    Row-Level Security / RBAC.
    """

    @staticmethod
    async def get_balances(
        session: AsyncSession, allowed_nodes: List[str], node_id: Optional[str] = None
    ) -> List[StockBalanceResponse]:

        # Base Query
        stmt = select(StockBalance)

        # Filter Logic (Layer B Authorization)
        if node_id:
            # We assume node_id access check happened at the entry point (API or Controller)
            # or we re-verify against the allowed_nodes list here for 'Defense in Depth'.
            if "GLOBAL" not in allowed_nodes and node_id not in allowed_nodes:
                return []  # Should technically be a 403, but this service returns data.
            stmt = stmt.where(StockBalance.node_id == node_id)
        else:
            # If requesting 'all', filter heavily to only what they are allowed to see
            if "GLOBAL" not in allowed_nodes:
                if not allowed_nodes:
                    return []  # Fast path return empty if they have no node rights
                stmt = stmt.where(StockBalance.node_id.in_(allowed_nodes))

        # Execute Query
        result = await session.execute(stmt)
        records = result.scalars().all()

        return [StockBalanceResponse.model_validate(r) for r in records]

    @staticmethod
    async def get_history(
        session: AsyncSession,
        allowed_nodes: List[str],
        node_id: str,
        item_id: str,
        limit: int = 50,
    ) -> List[LedgerHistoryResponse]:
        """
        Retrieves the immutable event log for a specific Node/Item combination.
        """
        # Security Filter
        if "GLOBAL" not in allowed_nodes and node_id not in allowed_nodes:
            return []  # Defense in Depth

        stmt = (
            select(InventoryEvent)
            .where(InventoryEvent.node_id == node_id, InventoryEvent.item_id == item_id)
            .order_by(InventoryEvent.occurred_at.desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        records = result.scalars().all()

        return [LedgerHistoryResponse.model_validate(r) for r in records]
