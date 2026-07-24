import datetime as dt

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import NoteStatus, SoapSection
from app.models.types import GUID, enum_column, new_uuid


class SoapNote(Base):
    """A single version of the compiled note for an encounter. New edits
    produce a new version rather than mutating a signed one, so the full
    version history is preserved."""

    __tablename__ = "soap_notes"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    encounter_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("encounters.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[NoteStatus] = mapped_column(enum_column(NoteStatus), default=NoteStatus.draft)
    signed_by: Mapped[GUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    signed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    encounter: Mapped["Encounter"] = relationship(back_populates="notes")
    lines: Mapped[list["SoapNoteLine"]] = relationship(
        back_populates="note", cascade="all, delete-orphan", order_by="SoapNoteLine.position"
    )


class SoapNoteLine(Base):
    """One line within a SOAP note section. Always references the claim(s)
    it was compiled from, so every line in the note is traceable back to the
    graph -- this is the join between the note and the evidence graph."""

    __tablename__ = "soap_note_lines"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    note_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("soap_notes.id"))
    section: Mapped[SoapSection] = mapped_column(enum_column(SoapSection))
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    # Comma-joined list of claim ids this line was compiled from. Kept as a
    # simple join table (SoapNoteLineClaim) rather than a plain string column
    # -- see relationship below.
    is_conflict: Mapped[bool] = mapped_column(default=False)
    # Rejected lines stay in the note (never silently deleted -- an
    # attestation already recorded the rejection) but are flagged so the UI
    # can grey them out instead of presenting them as part of the record.
    is_rejected: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    note: Mapped["SoapNote"] = relationship(back_populates="lines")
    claim_links: Mapped[list["SoapNoteLineClaim"]] = relationship(
        back_populates="line", cascade="all, delete-orphan"
    )


class SoapNoteLineClaim(Base):
    """Join row linking a note line to one of its source claims (a line may
    cite more than one claim, e.g. a contradiction shown side by side)."""

    __tablename__ = "soap_note_line_claims"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    line_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("soap_note_lines.id"))
    claim_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("claims.id"))

    line: Mapped["SoapNoteLine"] = relationship(back_populates="claim_links")
