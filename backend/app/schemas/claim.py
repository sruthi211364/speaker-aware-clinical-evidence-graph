import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ClaimStatus, ClaimType, SourceType


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    text: str
    claim_type: ClaimType
    source_type: SourceType
    source_reference: str | None
    confidence: float
    status: ClaimStatus
    normalized_code_system: str | None
    normalized_code: str | None
    normalized_display: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class EhrContextItem(BaseModel):
    """A structured EHR fact (existing condition, medication, allergy, ...).
    Already structured, so it becomes a Claim directly -- no LLM call needed,
    unlike free-text transcript segments."""

    claim_type: ClaimType
    text: str
    record_id: str | None = None


class EhrContextIngestRequest(BaseModel):
    items: list[EhrContextItem]
