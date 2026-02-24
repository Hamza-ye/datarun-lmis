import os
import sys
import logging
import asyncio
from uuid import uuid4
from datetime import date
from sqlalchemy import select, delete

# Add the 'backend' directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import async_session_maker
from app.kernel.models.registry import NodeRegistry, CommodityRegistry
from app.adapter.models.engine import MappingContract, AdapterCrosswalk

# Configure minimal logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def seed_staging_db():
    logger.info("Starting Staging DB Seed Process...")
    
    async with async_session_maker() as db:
        try:
            # Commodities
            result = await db.execute(select(CommodityRegistry).filter_by(item_id="AL_6x3"))
            if not result.scalars().first():
                db.add(CommodityRegistry(item_id="AL_6x3", code="AL_6x3", name="Artemether/Lumefantrine 20/120mg 6x3", base_unit="Blister", status="ACTIVE"))
                db.add(CommodityRegistry(item_id="RDT_PF", code="RDT_PF", name="Malaria RDT (Pf)", base_unit="Test", status="ACTIVE"))
                logger.info("Seeded CommodityRegistry items.")

            # Nodes (SCD Type 2)
            result = await db.execute(select(NodeRegistry).filter_by(uid="NMS_NATIONAL"))
            if not result.scalars().first():
                db.add(NodeRegistry(uid="NMS_NATIONAL", code="NMS", name="National Medical Stores", node_type="NATIONAL_WH", valid_from=date(2026, 1, 1)))
            
            result = await db.execute(select(NodeRegistry).filter_by(uid="DIST_A"))
            if not result.scalars().first():
                db.add(NodeRegistry(uid="DIST_A", code="DIST_A", name="District A Warehouse", node_type="DISTRICT_WH", parent_id="NMS_NATIONAL", valid_from=date(2026, 1, 1)))

            result = await db.execute(select(NodeRegistry).filter_by(uid="CLINIC_1"))
            if not result.scalars().first():
                db.add(NodeRegistry(uid="CLINIC_1", code="CLINIC_1", name="Clinic 1 (District A)", node_type="CLINIC", parent_id="DIST_A", valid_from=date(2026, 1, 1)))
            
            logger.info("Seeded NodeRegistry tree.")

            # Mapping Contract - FORCE OVERWRITE
            await db.execute(delete(MappingContract).where(MappingContract.id == "hf_receipt_902"))
            
            contract = MappingContract(
                id="hf_receipt_902",
                    version="v1",
                    status="ACTIVE",
                    dsl_config={
                        "contract_info": {
                            "id": "hf_receipt_902",
                            "version": "v1",
                            "status": "ACTIVE",
                            "source_system": "dhis2"
                        },
                        "ingress": {
                            "trigger_path": "$.type",
                            "trigger_value": "RECEIPT"
                        },
                        "destination": {
                            "url": "http://localhost:8000/api/ledger/commands",
                            "method": "POST"
                        },
                        "dictionaries": {
                            "external": {
                                "node_map": {
                                    "namespace": "dhis2",
                                    "on_unmapped": "ERROR"
                                },
                                "item_map": {
                                    "namespace": "lmis",
                                    "on_unmapped": "ERROR"
                                }
                            }
                        },
                        "processing_pipelines": {},
                        "output_template": [
                            {
                                "envelope": {
                                    "source_event_id": {"path": "$.source_event_id"},
                                    "timestamp": {"path": "$.date"}
                                },
                                "static_injection": {
                                    "command_type": "RECEIPT"
                                },
                                "global_fields": {
                                    "target_node": {
                                        "path": "$.facility_code",
                                        "dictionary": "external.node_map"
                                    }
                                },
                                "iterator": {
                                    "path": "$",
                                    "fields": {
                                        "item_id": {
                                            "path": "$.product_code",
                                            "dictionary": "external.item_map"
                                        },
                                        "quantity": {
                                            "path": "$.quantity_received"
                                        }
                                    }
                                }
                            }
                        ]
                    }
                )
            db.add(contract)
            logger.info("Seeded MappingContract.")

            # Adapter Crosswalk
            result = await db.execute(select(AdapterCrosswalk).filter_by(namespace="dhis2", source_value="C_1"))
            if not result.scalars().first():
                db.add(AdapterCrosswalk(
                    namespace="dhis2",
                    source_value="C_1",
                    internal_id="CLINIC_1"
                ))
            
            result = await db.execute(select(AdapterCrosswalk).filter_by(namespace="lmis", source_value="AL_6x3"))
            if not result.scalars().first():
                db.add(AdapterCrosswalk(
                    namespace="lmis",
                    source_value="AL_6x3",
                    internal_id="AL_6x3"
                ))
                
            logger.info("Seeded AdapterCrosswalk translations.")

            await db.commit()
            logger.info("Staging DB successfully seeded!")

        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to seed DB: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(seed_staging_db())
