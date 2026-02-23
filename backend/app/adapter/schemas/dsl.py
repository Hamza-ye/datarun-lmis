from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict, Union, Any, Optional

class ContractStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    DRAFT = "DRAFT"

class ContractInfo(BaseModel):
    id: str
    version: str
    status: ContractStatus
    source_system: str

class IngressConfig(BaseModel):
    trigger_path: str
    trigger_value: str

class DestinationConfig(BaseModel):
    url: str
    method: str = "POST"
    headers: Optional[Dict[str, str]] = None

class DictionaryConfig(BaseModel):
    namespace: str
    on_unmapped: str = Field(..., description="E.g., DLQ, PASS_THROUGH, ERROR")

class ExternalDictionaries(BaseModel):
    node_map: Optional[DictionaryConfig] = None
    item_map: Optional[DictionaryConfig] = None

class Dictionaries(BaseModel):
    external: ExternalDictionaries

class PipelineOp(BaseModel):
    op: str
    type: Optional[str] = None
    factor_from: Optional[str] = None
    value: Optional[Any] = None

class FieldExtraction(BaseModel):
    path: Optional[str] = None
    dictionary: Optional[str] = None
    pipeline: Optional[str] = None

class EnvelopeExtraction(BaseModel):
    source_event_id: FieldExtraction
    timestamp: FieldExtraction

class IteratorExtraction(BaseModel):
    path: str
    fields: Dict[str, FieldExtraction]

class OutputTemplateBlock(BaseModel):
    envelope: EnvelopeExtraction
    static_injection: Dict[str, Any]
    global_fields: Dict[str, FieldExtraction]
    iterator: IteratorExtraction

class MappingContractDSL(BaseModel):
    contract_info: ContractInfo
    ingress: IngressConfig
    destination: DestinationConfig
    dictionaries: Dictionaries
    processing_pipelines: Dict[str, List[PipelineOp]]
    output_template: List[OutputTemplateBlock]
