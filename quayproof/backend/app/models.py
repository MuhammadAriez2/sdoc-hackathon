from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ['BL_COMPARISON', 'SI_REQUEST', 'INVOICE_QUERY', 'GENERAL', 'SPAM']
FIELDS = ['shipper', 'consignee', 'notify_party', 'port_of_loading', 'port_of_discharge', 'container_count', 'gross_weight_kg']
Category = Literal['BL_COMPARISON', 'SI_REQUEST', 'INVOICE_QUERY', 'GENERAL', 'SPAM']
FieldName = Literal['shipper', 'consignee', 'notify_party', 'port_of_loading', 'port_of_discharge', 'container_count', 'gross_weight_kg']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Classification(StrictModel):
    category: Category
    reason: str = Field(max_length=1000)
    evidence: str = Field(max_length=1000)
    uncertain: bool


class Candidate(StrictModel):
    field: FieldName
    raw_value: str = Field(max_length=4000)
    block_ids: list[str] = Field(max_length=12)
    quote: str = Field(max_length=6000)
    uncertain: bool


class Extraction(StrictModel):
    doc_type: Literal['SI', 'BL', 'OTHER', 'UNKNOWN']
    type_block_id: str
    type_quote: str = Field(max_length=1000)
    fields: list[Candidate] = Field(max_length=28)


class RunRequest(StrictModel):
    version: int


class ReviewRequest(StrictModel):
    version: int
    action: Literal['correct_field', 'confirm_field', 'approve', 'classify']
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)
    document_id: str | None = None
    field: FieldName | None = None
    block_ids: list[str] = Field(default_factory=list, max_length=12)
    raw_value: str = Field(default='', max_length=4000)
    category: Category | None = None
