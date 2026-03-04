import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.kernel.domain.policy.resolver import PolicyResolver
from app.ledger.domain.event_store.service import EventStoreService
from app.ledger.models.in_transit import InternalDLQ, InTransitRegistry, InTransitStatus
from app.ledger.schemas.command import LedgerCommand, TransactionType


class InTransitService:
    @staticmethod
    async def process_dispatch(
        session: AsyncSession,
        command: LedgerCommand,
        dest_node_id: str,
    ) -> InTransitRegistry:
        """
        Step 1: The Departure.
        Deducts stock from source via the Event Store, and opens a tracking record.
        Uses PolicyResolver to determine auto_receive_days instead of hardcoded value.
        """
        if command.transaction_type != TransactionType.TRANSFER:
            raise ValueError(
                f"Dispatch requires TransactionType.TRANSFER, got {command.transaction_type}"
            )

        # 1. Deduct from Source (Event Store Math)
        await EventStoreService.commit_command(session, command)

        # 2. Resolve auto_receive_days from Policy Engine (fallback: 14 days)
        auto_receive_config = await PolicyResolver.get_policy(
            session,
            "policy.transfer.auto_receive_days",
            command.node_id,
            command.item_id,
        )
        auto_receive_days = 14  # Default fallback if no policy exists
        if auto_receive_config and "days" in auto_receive_config:
            auto_receive_days = auto_receive_config["days"]

        # 3. Open the Tracking Record
        registry = InTransitRegistry(
            source_node_id=command.node_id,
            dest_node_id=dest_node_id,
            item_id=command.item_id,
            qty_shipped=command.quantity,
            dispatched_at=command.occurred_at,
            auto_close_after=command.occurred_at
            + datetime.timedelta(days=auto_receive_days),
        )
        session.add(registry)
        await session.flush()

        return registry

    @staticmethod
    async def process_receipt(
        session: AsyncSession,
        command: LedgerCommand,
        transfer_id: str,
    ) -> InTransitRegistry:
        """
        Step 2: The Arrival.
        Credits stock to destination via the Event Store, and closes/updates the tracking record.
        """
        if command.transaction_type != TransactionType.RECEIPT:
            raise ValueError(
                f"Receipt requires TransactionType.RECEIPT, got {command.transaction_type}"
            )

        # 1. Fetch Tracking Record
        try:
            transfer_uuid = uuid.UUID(transfer_id)
        except ValueError:
            raise ValueError(f"Invalid transfer_id format: {transfer_id}")

        stmt = (
            select(InTransitRegistry)
            .where(InTransitRegistry.transfer_id == transfer_uuid)
            .with_for_update()
        )
        result = await session.execute(stmt)
        registry = result.scalars().first()

        if not registry:
            raise ValueError(f"No open transfer found with ID {transfer_id}")

        if registry.status not in [InTransitStatus.OPEN, InTransitStatus.PARTIAL]:
            raise ValueError(
                f"Transfer {transfer_id} is already in state {registry.status}"
            )

        # 2. Credit Destination (Event Store Math)
        await EventStoreService.commit_command(session, command)

        # 3. Update Tracking Record
        registry.qty_received += command.quantity

        if registry.qty_received >= registry.qty_shipped:
            registry.status = InTransitStatus.COMPLETED
        elif registry.qty_received > 0:
            registry.status = InTransitStatus.PARTIAL

        return registry

    @staticmethod
    async def auto_close_stale_transfers(session: AsyncSession) -> int:
        """
        Step 3: The Safety Net (Cron Job Target).
        Finds OPEN transfers past their deadline and auto-receives them.

        Doc invariant: "Partial transfers must NOT be silently auto-closed as STALE_AUTO_CLOSED.
        Auto-close applies only to OPEN transfers with zero receipts."
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # Only OPEN — exclude PARTIAL per documented invariant
        stmt = (
            select(InTransitRegistry)
            .where(
                InTransitRegistry.status == InTransitStatus.OPEN,
                InTransitRegistry.auto_close_after < now,
            )
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(stmt)
        stale_records = result.scalars().all()

        count = 0
        for record in stale_records:
            missing_qty = record.qty_shipped - record.qty_received

            if missing_qty <= 0:
                record.status = InTransitStatus.COMPLETED
                continue

            # Synthesize an Auto-Receipt Command
            auto_receipt_cmd = LedgerCommand(
                source_event_id=f"AUTO_RECV_{record.transfer_id}",
                version_timestamp=int(now.timestamp()),
                transaction_type=TransactionType.RECEIPT,
                node_id=record.dest_node_id,
                item_id=record.item_id,
                quantity=missing_qty,
                transfer_id=str(record.transfer_id),
                occurred_at=now,
                metadata={"reason": "SYSTEM_AUTO_CLOSE"},
            )

            nested = await session.begin_nested()
            try:
                await EventStoreService.commit_command(session, auto_receipt_cmd)
                record.qty_received += missing_qty
                record.status = InTransitStatus.STALE_AUTO_CLOSED
                await nested.commit()
                count += 1
            except Exception as e:
                await nested.rollback()
                record.status = InTransitStatus.FAILED_AUTO_CLOSE

                dlq_entry = InternalDLQ(
                    source_process="AREA_D_AUTO_RECEIPT",
                    reference_id=str(record.transfer_id),
                    error_message=str(e),
                )
                session.add(dlq_entry)

        await session.commit()
        return count

    @staticmethod
    async def process_loss(
        session: AsyncSession,
        command: LedgerCommand,
        transfer_id: str,
    ) -> InTransitRegistry:
        """
        Step 4: The Write-Off.
        Resolves a physically lost shipment using TransactionType.ADJUSTMENT
        with adjustment_reason='LOSS_IN_TRANSIT'.
        Marks the tracking record as LOST_IN_TRANSIT to prevent auto-receipt cron.
        Writes a $0-value accountability event to the Event Store for the source node.
        """
        if command.transaction_type != TransactionType.ADJUSTMENT:
            raise ValueError(
                f"Loss requires TransactionType.ADJUSTMENT, got {command.transaction_type}"
            )

        if command.adjustment_reason != "LOSS_IN_TRANSIT":
            raise ValueError(
                f"Loss requires adjustment_reason='LOSS_IN_TRANSIT', got '{command.adjustment_reason}'"
            )

        try:
            transfer_uuid = uuid.UUID(transfer_id)
        except ValueError:
            raise ValueError(f"Invalid transfer_id format: {transfer_id}")

        stmt = (
            select(InTransitRegistry)
            .where(InTransitRegistry.transfer_id == transfer_uuid)
            .with_for_update()
        )
        result = await session.execute(stmt)
        registry = result.scalars().first()

        if not registry:
            raise ValueError(f"No open transfer found with ID {transfer_id}")

        if registry.status not in [InTransitStatus.OPEN, InTransitStatus.PARTIAL]:
            raise ValueError(
                f"Transfer {transfer_id} is already in state {registry.status}, cannot write off."
            )

        # Write accountability audit event (Delta = 0 to avoid double-deduction since Dispatch already deducted)
        zero_command = command.model_copy(update={"quantity": 0})
        await EventStoreService.commit_command(session, zero_command)

        # Update Tracking Record
        registry.status = InTransitStatus.LOST_IN_TRANSIT

        return registry
