import datetime as dt

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ClaimStatus, ClaimType, SourceType
from app.models.types import GUID, enum_column, new_uuid


class Claim(Base):
    """One atomic clinical statement extracted from the encounter or an
    external source, with a required pointer back to where it came from."""

    __tablename__ = "claims"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    encounter_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("encounters.id"))

    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[ClaimType] = mapped_column(enum_column(ClaimType))
    source_type: Mapped[SourceType] = mapped_column(enum_column(SourceType))

    # Pointer to the transcript segment id, EHR record id, or device reading
    # id this claim was extracted from. Free-form string rather than an FK
    # since the referent table depends on source_type.
    source_reference: Mapped[str | None] = mapped_column(nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[ClaimStatus] = mapped_column(
        enum_column(ClaimStatus), default=ClaimStatus.proposed
    )

    # Terminology normalization (wired in Phase 6)
    normalized_code_system: Mapped[str | None] = mapped_column(nullable=True)  # RxNorm | SNOMED | LOINC
    normalized_code: Mapped[str | None] = mapped_column(nullable=True)
    normalized_display: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    encounter: Mapped["Encounter"] = relationship(back_populates="claims")
    outgoing_edges: Mapped[list["ClaimEdge"]] = relationship(
        back_populates="source_claim",
        foreign_keys="ClaimEdge.source_claim_id",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["ClaimEdge"]] = relationship(
        back_populates="target_claim",
        foreign_keys="ClaimEdge.target_claim_id",
        cascade="all, delete-orphan",
    )
