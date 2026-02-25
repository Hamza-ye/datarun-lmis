import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.main import app
from core.database import async_session_maker

async def reset_db():
    print("WARNING: This will DESTROY all data in the LIMS. Press Ctrl+C to abort.")
    await asyncio.sleep(2)  # Give user a chance to cancel
    
    async with async_session_maker() as session:
        try:
            # We want to clear tables in the correct dependency order.
            # Using raw SQL to safely TRUNCATE and CASCADE to avoid foreign key violations.
            
            tables_to_truncate = [
                "adapter_inbox",
                "adapter_crosswalk",
                "mapping_contracts",
                "event_store_inventory",
                "event_store_balances",
                "staged_commands",
                "gatekeeper_audit",
                "idempotency_registry",
                "in_transit_transfers",
                "in_transit_events",
                "kernel_node_registry",
                "kernel_commodity_registry",
            ]
            
            print("Truncating tables...")
            for table in tables_to_truncate:
                # Add CASCADE to handle any unforeseen foreign key relationships
                stmt = f"TRUNCATE TABLE {table} CASCADE;"
                try:
                    async with session.begin_nested():
                        await session.execute(text(stmt))
                    print(f" - Truncated {table}")
                except Exception as e:
                    # Ignore if table doesn't exist etc.
                    print(f" - Warning: Could not truncate {table}: {e}")
            
            await session.commit()
            print("\nDatabase reset successful! The schemas are intact but all data is gone.")
        except Exception as e:
            await session.rollback()
            print(f"Failed to reset database: {e}")

if __name__ == "__main__":
    asyncio.run(reset_db())
