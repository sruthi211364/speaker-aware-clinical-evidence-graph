import datetime as dt

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EncounterStatus
from app.models.types import GUID, enum_column, new_uuid


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    patient_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("users.id"))
    clinician_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("users.id"))
    started_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    status: Mapped[EncounterStatus] = mapped_column(
        enum_column(EncounterStatus), default=EncounterStatus.in_progress
    )
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    notes: Mapped[list["SoapNote"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
