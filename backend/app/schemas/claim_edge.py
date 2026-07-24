import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EdgeRelation
from app.schemas.claim import ClaimRead


class ClaimEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_claim_id: uuid.UUID
    target_claim_id: uuid.UUID
    relation: EdgeRelation
    rationale: str | None
    confidence: float
    created_at: dt.datetime


class ClaimGraphResponse(BaseModel):
    claims: list[ClaimRead]
    edges: list[ClaimEdgeRead]
