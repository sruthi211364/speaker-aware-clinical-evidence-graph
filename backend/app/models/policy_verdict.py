import datetime as dt

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import PolicyCheckType
from app.models.types import GUID, enum_column, new_uuid


class PolicyVerdict(Base):
    """One check result from the zero-trust policy engine for one claim.
    Five verdicts are produced per claim (support, contradiction,
    temporal_ambiguity, missing_context, clinical_safety). A failed verdict
    updates the claim's status and, for missing_context, spawns a
    ClarificationQuestion rather than letting the model silently guess."""

    __tablename__ = "policy_verdicts"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    claim_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("claims.id"))
    check_type: Mapped[PolicyCheckType] = mapped_column(enum_column(PolicyCheckType))
    passed: Mapped[bool] = mapped_column()
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
