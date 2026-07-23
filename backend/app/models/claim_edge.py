import datetime as dt

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EdgeRelation
from app.models.types import GUID, enum_column, new_uuid


class ClaimEdge(Base):
    """A directed, typed relationship between two claims. This is what makes
    the claim store a graph rather than a flat list: contradicts edges power
    the conflicting-accounts view, supports/refines edges corroborate a
    claim, duplicates edges collapse restatements."""

    __tablename__ = "claim_edges"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    source_claim_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("claims.id"))
    target_claim_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("claims.id"))
    relation: Mapped[EdgeRelation] = mapped_column(enum_column(EdgeRelation))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    source_claim: Mapped["Claim"] = relationship(
        back_populates="outgoing_edges", foreign_keys=[source_claim_id]
    )
    target_claim: Mapped["Claim"] = relationship(
        back_populates="incoming_edges", foreign_keys=[target_claim_id]
    )
