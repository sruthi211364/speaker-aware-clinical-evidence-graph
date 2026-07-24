import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import PolicyCheckType


class PolicyVerdictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    check_type: PolicyCheckType
    passed: bool
    rationale: str | None
    created_at: dt.datetime


class ClarificationQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    triggering_claim_id: uuid.UUID
    question_text: str
    grounding_citation_id: uuid.UUID | None
    resolved: bool
    resolved_by_claim_id: uuid.UUID | None
    created_at: dt.datetime
    resolved_at: dt.datetime | None


class ClarificationAnswerRequest(BaseModel):
    answer_text: str


class PipelineRunResult(BaseModel):
    encounter_id: str
    transcript_segment_count: int = 0
    claim_count: int = 0
    edge_count: int = 0
    citation_count: int = 0
    verdict_count: int = 0
    open_clarification_count: int = 0
    normalized_claim_count: int = 0
    note_id: str | None = None
    note_version: int | None = None
    awaiting_review: bool = False


class PipelineTraceEntry(BaseModel):
    node: str | None
    step: int | None
    next: list[str]
    result: dict | None = None
    values: dict
