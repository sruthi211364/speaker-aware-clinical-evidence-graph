import datetime as dt

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AttestationAction
from app.models.types import GUID, enum_column, new_uuid
from app.db import Base


class Attestation(Base):
    """A timestamped, attributable record of a clinician action on a claim or
    note line. The full ordered sequence of attestations for an encounter is
    the audit lineage from transcript to signed record."""

    __tablename__ = "attestations"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    encounter_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("encounters.id"))
    note_version_id: Mapped[GUID | None] = mapped_column(
        GUID(), ForeignKey("soap_notes.id"), nullable=True
    )
    note_line_id: Mapped[GUID | None] = mapped_column(
        GUID(), ForeignKey("soap_note_lines.id"), nullable=True
    )
    claim_id: Mapped[GUID | None] = mapped_column(GUID(), ForeignKey("claims.id"), nullable=True)
    actor_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("users.id"))
    action: Mapped[AttestationAction] = mapped_column(enum_column(AttestationAction))
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
