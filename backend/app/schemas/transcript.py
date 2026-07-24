import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SpeakerRole


class TranscriptSegmentIn(BaseModel):
    speaker_role: SpeakerRole
    speaker_identifier: str | None = None
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TranscriptIngestRequest(BaseModel):
    segments: list[TranscriptSegmentIn]


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    speaker_role: SpeakerRole
    speaker_identifier: str | None
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    created_at: dt.datetime
