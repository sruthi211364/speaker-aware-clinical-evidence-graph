import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.knowledge_chunk import EMBEDDING_DIM
from app.models.types import GUID, new_uuid


class VocabularyTerm(Base):
    """One entry in the terminology normalization index: a coded concept
    from RxNorm (medications), SNOMED CT (conditions/findings), or LOINC
    (observations/vitals), embedded for semantic lookup. A small curated
    subset relevant to this prototype's demo scenarios, not a full
    vocabulary download -- see README for why."""

    __tablename__ = "vocabulary_terms"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    code_system: Mapped[str] = mapped_column()  # "RxNorm" | "SNOMED" | "LOINC"
    code: Mapped[str] = mapped_column()
    display: Mapped[str] = mapped_column()
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
