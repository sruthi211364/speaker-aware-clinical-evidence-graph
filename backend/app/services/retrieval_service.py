"""Retrieval over the two RAG indexes described in the project brief: the
clinical knowledge index (guideline snippets, drug interaction data,
per-symptom documentation requirements) and the longitudinal patient history
index (a patient's prior encounter notes). Grounds claims and, from Phase 5,
policy verdicts in real clinical context instead of the model's unaided
judgment.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import ClinicalKnowledgeChunk, PatientHistoryChunk, VocabularyTerm
from app.services.embedding_service import embed_query


def retrieve_clinical_knowledge(
    db: Session, query: str, top_k: int = 3
) -> list[tuple[ClinicalKnowledgeChunk, float]]:
    """Returns up to top_k (chunk, similarity) pairs, most relevant first."""
    query_vec = embed_query(query)
    distance = ClinicalKnowledgeChunk.embedding.cosine_distance(query_vec)
    rows = (
        db.query(ClinicalKnowledgeChunk, distance.label("distance"))
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    return [(chunk, 1.0 - dist) for chunk, dist in rows]


def retrieve_vocabulary_term(
    db: Session, code_system: str, query: str
) -> tuple[VocabularyTerm, float] | None:
    """Returns the single closest vocabulary term within one code system
    (RxNorm/SNOMED/LOINC), or None if the index has no terms for that
    system. Used by terminology normalization (Phase 6) to map a claim's
    free-text concept to a standardized code."""
    query_vec = embed_query(query)
    distance = VocabularyTerm.embedding.cosine_distance(query_vec)
    row = (
        db.query(VocabularyTerm, distance.label("distance"))
        .filter(VocabularyTerm.code_system == code_system)
        .order_by(distance)
        .first()
    )
    if row is None:
        return None
    term, dist = row
    return term, 1.0 - dist


def retrieve_patient_history(
    db: Session, patient_id: uuid.UUID, query: str, top_k: int = 3
) -> list[tuple[PatientHistoryChunk, float]]:
    """Returns up to top_k (chunk, similarity) pairs scoped to this patient's
    prior encounters, most relevant first."""
    query_vec = embed_query(query)
    distance = PatientHistoryChunk.embedding.cosine_distance(query_vec)
    rows = (
        db.query(PatientHistoryChunk, distance.label("distance"))
        .filter(PatientHistoryChunk.patient_id == patient_id)
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    return [(chunk, 1.0 - dist) for chunk, dist in rows]
