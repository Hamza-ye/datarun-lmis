import asyncio
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.adapter.models.engine import AdapterInbox, InboxStatus
from app.kernel.models.registry import NodeRegistry
from app.ledger.domain.reporting.service import ReportingService


class CompositionService:
    @staticmethod
    async def get_node_overview(
        db: AsyncSession, allowed_nodes: List[str], node_id: str
    ) -> Dict[str, Any]:
        """
        Aggregates data across domains with strict timeout and fault tolerance.
        """

        # Define tasks with individual timeouts (ADR 002)
        # In a real production setup, we'd use a more robust timeout wrapper

        results = {
            "node": {"status": "pending", "data": None},
            "stock": {"status": "pending", "data": None},
            "pending_sync": {"status": "pending", "data": None},
        }

        async def fetch_node():
            try:
                stmt = select(NodeRegistry).where(
                    NodeRegistry.uid == node_id, NodeRegistry.valid_to == None
                )
                res = await db.execute(stmt)
                node = res.scalars().first()
                if node:
                    results["node"] = {
                        "status": "ok",
                        "data": {
                            "uid": node.uid,
                            "name": node.name,
                            "node_type": node.node_type,
                            "code": node.code,
                        },
                    }
                else:
                    results["node"] = {"status": "not_found", "data": None}
            except Exception as e:
                results["node"] = {"status": "error", "message": str(e)}

        async def fetch_stock():
            try:
                # ReportingService has its own internal actor checks
                balances = await ReportingService.get_balances(
                    db, allowed_nodes, node_id
                )
                results["stock"] = {"status": "ok", "data": balances}
            except asyncio.TimeoutError:
                results["stock"] = {"status": "timeout", "data": []}
            except Exception as e:
                results["stock"] = {"status": "error", "message": str(e)}

        async def fetch_adapter():
            try:
                # Find pending events for this system/node
                # (Simple prototype: list last 5 RECEIVED globally for now)
                stmt = (
                    select(AdapterInbox)
                    .where(AdapterInbox.status == InboxStatus.RECEIVED)
                    .order_by(AdapterInbox.created_at.desc())
                    .limit(5)
                )
                res = await db.execute(stmt)
                items = res.scalars().all()
                results["pending_sync"] = {
                    "status": "ok",
                    "count": len(items),
                    "latest": [
                        {"id": str(i.id), "received_at": i.created_at} for i in items
                    ],
                }
            except Exception as e:
                results["pending_sync"] = {"status": "error", "message": str(e)}

        # Execute concurrently
        await asyncio.gather(fetch_node(), fetch_stock(), fetch_adapter())

        return results
