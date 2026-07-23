import datetime as dt

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import SpeakerRole
from app.models.types import GUID, enum_column, new_uuid


class TranscriptSegment(Base):
    """One utterance in an encounter: a speaker-labeled, timestamped span of
    raw text. This is the atomic unit that claims are grounded against."""

    __tablename__ = "transcript_segments"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    encounter_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("encounters.id"))
    speaker_role: Mapped[SpeakerRole] = mapped_column(enum_column(SpeakerRole))
    speaker_identifier: Mapped[str | None] = mapped_column(nullable=True)
    start_ms: Mapped[int] = mapped_column()
    end_ms: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    encounter: Mapped["Encounter"] = relationship(back_populates="transcript_segments")
