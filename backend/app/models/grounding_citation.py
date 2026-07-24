import datetime as dt

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import GroundingSourceType
from app.models.types import GUID, enum_column, new_uuid


class GroundingCitation(Base):
    """Links a claim (or a policy verdict) to a retrieved external reference
    -- a guideline snippet, a drug interaction record, or a prior encounter
    note. This is what turns a policy decision from "the model said so" into
    "the model said so, and here is the retrieved evidence it used." Claim
    citations populated starting in Phase 4; verdict citations in Phase 5."""

    __tablename__ = "grounding_citations"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    claim_id: Mapped[GUID | None] = mapped_column(GUID(), ForeignKey("claims.id"), nullable=True)
    verdict_id: Mapped[GUID | None] = mapped_column(
        GUID(), ForeignKey("policy_verdicts.id"), nullable=True
    )
    source_type: Mapped[GroundingSourceType] = mapped_column(enum_column(GroundingSourceType))
    source_identifier: Mapped[str | None] = mapped_column(nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
