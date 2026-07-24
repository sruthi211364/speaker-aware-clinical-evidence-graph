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


class TranscribedUtteranceOut(BaseModel):
    speaker_label: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None


class AudioTranscriptionPreview(BaseModel):
    """The raw diarized output of one audio upload, not yet persisted.
    speaker_labels lists every distinct label AssemblyAI assigned (e.g.
    ["A", "B"]) so the caller knows exactly which ones it must map to a
    SpeakerRole before committing -- nothing is guessed."""

    utterances: list[TranscribedUtteranceOut]
    speaker_labels: list[str]


class AudioTranscriptCommitRequest(BaseModel):
    """Commits a previously previewed transcription. speaker_role_map must
    cover every speaker_label present in `utterances`, or the commit is
    rejected -- an utterance is never silently dropped for lacking a
    mapping."""

    utterances: list[TranscribedUtteranceOut]
    speaker_role_map: dict[str, SpeakerRole]
