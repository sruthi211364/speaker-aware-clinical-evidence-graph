import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import GroundingSourceType


class GroundingCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID | None
    source_type: GroundingSourceType
    source_identifier: str | None
    excerpt: str | None
    relevance_score: float
    created_at: dt.datetime
