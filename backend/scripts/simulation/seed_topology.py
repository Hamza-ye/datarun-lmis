import asyncio
import sys
import os
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.ext.asyncio import AsyncSession
from core.database import async_session_maker
from app.kernel.models.registry import NodeRegistry, CommodityRegistry
from app.adapter.models.engine import MappingContract

async def seed_topology():
    print("Seeding baseline simulation topology...")
    
    async with async_session_maker() as session:
        try:
            # 1. Base Commodities
            item1 = CommodityRegistry(item_id="AMOX_250", code="AMX250", name="Amoxicillin 250mg", base_unit="CAPSULE")
            item2 = CommodityRegistry(item_id="PARA_500", code="PAR500", name="Paracetamol 500mg", base_unit="TABLET")
            session.add_all([item1, item2])
            
            # 2. Base Topology
            hq = NodeRegistry(uid="HQ", code="HQ", name="National Central Medical Store", node_type="NATIONAL", valid_from=datetime.date(1990, 1, 1))
            dist_n = NodeRegistry(uid="DIST_N", code="DIST_N", name="North District Store", node_type="DISTRICT", parent_id="HQ", valid_from=datetime.date(1990, 1, 1))
            clinic_a = NodeRegistry(uid="CLINIC_A", code="CLINIC_A", name="River Clinic A", node_type="CLINIC", parent_id="DIST_N", valid_from=datetime.date(1990, 1, 1))
            clinic_b = NodeRegistry(uid="CLINIC_B", code="CLINIC_B", name="Mountain Clinic B", node_type="CLINIC", parent_id="DIST_N", valid_from=datetime.date(1990, 1, 1))
            
            session.add_all([hq, dist_n, clinic_a, clinic_b])
            
            # 3. Required Adapter Mapping Contract to accept Firehose Simulation Playloads
            dsl_config = {
                "contract_info": {
                    "source_system": "FIREHOSE_SIM",
                    "contract_version": "1.0",
                    "dest_domain": "LEDGER_CORE"
                },
                "ingress": {
                    "envelope": "data",
                    "items_array": "entries"
                },
                "routing": {
                    "node_id": "clinic_code",
                    "occurred_at": "timestamp"
                },
                "dictionaries": {
                    "external": {
                        "node_map": {"namespace": "sim_nodes", "on_unmapped": "PASS_THROUGH"},
                        "item_map": {"namespace": "sim_items", "on_unmapped": "PASS_THROUGH"}
                    }
                },
                "pipelines": {
                    "quantity": [
                        {"operation": "convert_type", "type": "int"},
                        {"operation": "multiply_by_factor", "factor_path": "pack_size", "default_factor": 1}
                    ]
                },
                "output_template": {
                    "transaction_type": "transaction_type",
                    "item_id": "item_code",
                    "quantity": "computed:quantity",
                    "source_event_id": "event_uuid"
                }
            }
            
            contract = MappingContract(id="FIREHOSE_V1", version="1.0", status="ACTIVE", dsl_config=dsl_config)
            session.add(contract)
            
            await session.commit()
            print("Successfully seeded HQ, DIST_N, CLINIC_A, CLINIC_B, AMOX_250, PARA_500, and FIREHOSE_V1 contract.")
        except Exception as e:
            await session.rollback()
            print(f"Failed to seed topology: {e}")

if __name__ == "__main__":
    asyncio.run(seed_topology())
