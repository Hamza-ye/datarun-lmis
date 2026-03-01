from typing import Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.adapter.engine.json_path_extractor import JsonPathExtractor
from app.adapter.engine.pipeline_runner import PipelineRunner
from app.adapter.models.engine import AdapterCrosswalk
from app.adapter.schemas.dsl import MappingContractDSL


class MapperEngine:
    
    @staticmethod
    async def run(session: AsyncSession, payload: dict, contract: MappingContractDSL) -> List[dict]:
        """
        Executes the JSON mapping contract against the inbound payload.
        Returns a list of resulting LedgerCommand JSON bodies.
        """
        results = []
        
        # We need to process each output template block
        for block in contract.output_template:
            
            # --- 1. Envelope Extraction ---
            source_event_id = JsonPathExtractor.extract_single(payload, block.envelope.source_event_id.path)
            timestamp = JsonPathExtractor.extract_single(payload, block.envelope.timestamp.path)
            
            if not source_event_id or not timestamp:
                raise ValueError(f"DLQ_TRIGGER: Missing required envelope fields (source_event_id/timestamp) for mapped path. ID: {source_event_id}, TS: {timestamp}")
            
            # --- 2. Static Injections (e.g. command_type: RECEIPT) ---
            static_fields = block.static_injection
            
            # --- 3. Global Field Extraction & Dictionary Lookup ---
            global_resolved = {}
            for field_name, extraction_config in block.global_fields.items():
                raw_value = JsonPathExtractor.extract_single(payload, extraction_config.path)
                
                # Check dictionary lookup
                if extraction_config.dictionary:
                    resolved, _, _ = await MapperEngine._resolve_dictionary(
                        session, contract, extraction_config.dictionary, raw_value
                    )
                    global_resolved[field_name] = resolved
                else:
                    global_resolved[field_name] = raw_value

            # --- 4. Iterator Extraction ---
            items_array = JsonPathExtractor.extract_list(payload, block.iterator.path)
            
            for index, item_ctx in enumerate(items_array):
                transaction = {
                    "source_event_id": f"{source_event_id}_{index}",
                    "version_timestamp": int(timestamp.replace("-", "").replace(":", "").replace("T", "").replace("Z", "")) if isinstance(timestamp, str) else timestamp,
                    "transaction_type": static_fields.get("command_type"),
                    "occurred_at": timestamp
                }
                
                for g_k, g_v in global_resolved.items():
                    map_key = "node_id" if g_k == "target_node" else g_k
                    transaction[map_key] = g_v

                # We need to build a shared context of all dictionary looks ups for this item
                # so that pipelines on a field can reference dictionary data from another field.
                shared_dict_context = {}
                raw_values_cache = {}

                # First Pass: Extract and Resolve Dictionaries
                for field_name, line_config in block.iterator.fields.items():
                    relative_path = line_config.path
                    if relative_path.startswith("$."):
                        relative_path = relative_path[2:]
                    
                    raw_line_val = item_ctx.get(relative_path)
                    raw_values_cache[field_name] = raw_line_val
                    
                    if line_config.dictionary:
                        resolved_val, dict_metadata, dict_name = await MapperEngine._resolve_dictionary(
                            session, contract, line_config.dictionary, raw_line_val
                        )
                        transaction[field_name] = resolved_val
                        if dict_name:
                            shared_dict_context[dict_name] = {"metadata": dict_metadata}
                    else:
                        transaction[field_name] = raw_line_val
                        
                # Second Pass: Run Pipelines
                for field_name, line_config in block.iterator.fields.items():
                    if line_config.pipeline:
                        ops = contract.processing_pipelines.get(line_config.pipeline, [])
                        transaction[field_name] = PipelineRunner.execute(
                            transaction[field_name], ops, dictionary_lookup_result=shared_dict_context
                        )

                results.append(transaction)

        return results

    @staticmethod
    async def _resolve_dictionary(session: AsyncSession, contract: MappingContractDSL, dict_reference: str, raw_value: Any) -> tuple[Any, dict, str]:
        """
        Looks up `raw_value` in the `adapter_crosswalks` table based on the dictionary configuration.
        Returns a tuple: (mapped_internal_id, metadata_json_dict, dict_name)
        """
        if not dict_reference.startswith("external:"):
            return raw_value, {}, None
            
        dict_name = dict_reference.split(":")[1] # e.g. 'node_map' or 'item_map'
        dict_config = None
        
        # Find config
        if dict_name == "node_map" and contract.dictionaries.external.node_map:
            dict_config = contract.dictionaries.external.node_map
        elif dict_name == "item_map" and contract.dictionaries.external.item_map:
            dict_config = contract.dictionaries.external.item_map
            
        if not dict_config:
            return raw_value, {}, dict_name
            
        stmt = select(AdapterCrosswalk).where(
            AdapterCrosswalk.namespace == dict_config.namespace,
            AdapterCrosswalk.source_value == str(raw_value)
        )
        
        result = await session.execute(stmt)
        record = result.scalars().first()
        
        if record:
             return record.internal_id, record.metadata_json or {}, dict_name
             
        # Unmapped behavior
        if dict_config.on_unmapped == "PASS_THROUGH":
            return raw_value, {}, dict_name
        elif dict_config.on_unmapped == "USE_DEFAULT":
            return dict_config.default_value, {}, dict_name
        elif dict_config.on_unmapped == "DLQ":
            raise ValueError(f"DLQ_TRIGGER: Unmapped value '{raw_value}' in namespace '{dict_config.namespace}'")
        elif dict_config.on_unmapped == "ERROR":
            raise Exception(f"Strict mapping failed for value '{raw_value}'")
            
        return raw_value, {}, dict_name
