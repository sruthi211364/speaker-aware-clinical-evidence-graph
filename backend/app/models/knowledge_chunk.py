import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID, new_uuid

# bge-small-en-v1.5 (via fastembed) produces 384-dim vectors. A local model is
# used instead of a hosted embeddings API (e.g. Voyage AI, which Anthropic
# recommends for production) so this prototype doesn't need a second paid API
# key beyond ANTHROPIC_API_KEY -- see README for the tradeoff.
EMBEDDING_DIM = 384


class ClinicalKnowledgeChunk(Base):
    """One chunk of the clinical knowledge index: a guideline snippet, a drug
    interaction fact, or a per-symptom documentation requirement. Retrieved
    to ground policy engine checks (Phase 5) in real clinical context instead
    of the model's unaided judgment."""

    __tablename__ = "clinical_knowledge_chunks"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    source_identifier: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    # "documentation_standard" | "drug_interaction" -- lets the grounding
    # endpoint tag citations as GroundingSourceType.guideline vs .drug_data,
    # which Phase 5's clinical safety check depends on to find drug/allergy
    # interaction evidence specifically, not just any guideline hit.
    category: Mapped[str] = mapped_column(default="documentation_standard")
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class PatientHistoryChunk(Base):
    """One chunk of a patient's longitudinal history index: a note or
    statement from a prior encounter. Retrieved to catch cases like a
    symptom being described differently than at a previous visit."""

    __tablename__ = "patient_history_chunks"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    patient_id: Mapped[GUID] = mapped_column(GUID())
    source_encounter_label: Mapped[str] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
