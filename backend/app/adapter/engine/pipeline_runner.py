from typing import Any, List
from app.adapter.schemas.dsl import PipelineOp

class PipelineRunner:
    """
    Executes a sequence of mathematical or casting operations against an initial value.
    This eliminates hardcoded python if/else logic for specific UoM conversions.
    """
    
    @staticmethod
    def execute(initial_value: Any, pipeline_ops: List[PipelineOp], dictionary_lookup_result: dict = None) -> Any:
        current_value = initial_value
        is_int = False
        
        for op_config in pipeline_ops:
            if current_value is None:
                break # Cannot pipe a None value
                
            if op_config.op == "cast":
                if op_config.type == "INTEGER":
                    try:
                        current_value = int(current_value)
                        is_int = True
                    except ValueError:
                        raise ValueError(f"Pipeline cast to INTEGER failed for value: '{current_value}'")
                        
            elif op_config.op == "multiply":
                factor = 1.0
                
                if op_config.value is not None:
                    factor = float(op_config.value)
                elif op_config.factor_from and dictionary_lookup_result:
                    # e.g., "dictionary.item_map.metadata.transform_factor"
                    # We expect dictionary_lookup_result to contain ALL mapped dictionary results for this context
                    # Example: {"item_map": {"metadata": {"transform_factor": 25}}}
                    
                    # Hacky but effective static path parsing for MVP
                    try:
                        parts = op_config.factor_from.split(".")
                        dict_name = parts[1] # item_map
                        
                        if dict_name in dictionary_lookup_result:
                            meta = dictionary_lookup_result[dict_name].get("metadata", {})
                            if "transform_factor" in meta:
                                factor = float(meta["transform_factor"])
                    except (IndexError, AttributeError):
                        pass

                current_value = float(current_value) * factor
                
                if is_int:
                    current_value = int(current_value)

        return current_value
