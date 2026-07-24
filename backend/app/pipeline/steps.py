"""Pipeline step functions, one per pipeline stage (extract claims -> build
graph -> ground claims -> run policy engine). Shared between the individual
per-stage REST endpoints (app/api/claims.py, graph.py, grounding.py -- kept
for direct/manual triggering and inspection) and the LangGraph-orchestrated
full-pipeline run (app/pipeline/graph.py, Phase 5). Both callers share this
one implementation so there is exactly one place each stage's logic lives.

Each function takes a DB session and an Encounter and is idempotent per
encounter, matching the behavior the individual endpoints already had.
"""

from sqlalchemy.orm import Session

from app.models import Claim, ClaimEdge, Encounter, GroundingCitation, PolicyVerdict, TranscriptSegment
from app.models.enums import ClaimStatus, ClaimType, EdgeRelation, GroundingSourceType, SourceType, SpeakerRole
from app.services.claude_service import (
    ClaimForEdgeInput,
    TranscriptSegmentInput,
    extract_claims_from_transcript,
    generate_claim_edges,
)
from app.services.policy_engine import run_policy_engine_for_claim
from app.services.retrieval_service import retrieve_clinical_knowledge, retrieve_patient_history

_SPEAKER_TO_SOURCE_TYPE = {
    SpeakerRole.patient: SourceType.patient_speech,
    SpeakerRole.caregiver: SourceType.caregiver_report,
    SpeakerRole.clinician: SourceType.clinician_observation,
}
_EXTRACTABLE_ROLES = set(_SPEAKER_TO_SOURCE_TYPE)
_GROUNDING_TOP_K = 2


def extract_claims_step(db: Session, encounter: Encounter) -> list[Claim]:
    existing = (
        db.query(Claim)
        .filter(
            Claim.encounter_id == encounter.id,
            Claim.source_type.in_(list(_SPEAKER_TO_SOURCE_TYPE.values())),
        )
        .all()
    )
    if existing:
        return existing

    segments = (
        db.query(TranscriptSegment)
        .filter_by(encounter_id=encounter.id)
        .order_by(TranscriptSegment.start_ms)
        .all()
    )
    extractable = [s for s in segments if s.speaker_role in _EXTRACTABLE_ROLES]

    model_input = [
        TranscriptSegmentInput(index=i, speaker_role=s.speaker_role.value, text=s.text)
        for i, s in enumerate(extractable)
    ]
    result = extract_claims_from_transcript(model_input)

    claims: list[Claim] = []
    for extracted in result.claims:
        if not (0 <= extracted.source_segment_index < len(extractable)):
            continue
        segment = extractable[extracted.source_segment_index]
        claims.append(
            Claim(
                encounter_id=encounter.id,
                text=extracted.text,
                claim_type=ClaimType(extracted.claim_type),
                source_type=_SPEAKER_TO_SOURCE_TYPE[segment.speaker_role],
                source_reference=str(segment.id),
                confidence=extracted.confidence,
                status=ClaimStatus.proposed,
            )
        )
    db.add_all(claims)
    db.commit()
    for c in claims:
        db.refresh(c)
    return claims


def build_graph_step(db: Session, encounter: Encounter) -> list[ClaimEdge]:
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    claim_ids = [c.id for c in claims]

    existing = (
        db.query(ClaimEdge).filter(ClaimEdge.source_claim_id.in_(claim_ids)).all() if claim_ids else []
    )
    if existing:
        return existing
    if len(claims) < 2:
        return []

    model_input = [
        ClaimForEdgeInput(index=i, claim_type=c.claim_type.value, source_type=c.source_type.value, text=c.text)
        for i, c in enumerate(claims)
    ]
    result = generate_claim_edges(model_input)

    edges: list[ClaimEdge] = []
    for extracted in result.edges:
        if not (0 <= extracted.source_claim_index < len(claims)):
            continue
        if not (0 <= extracted.target_claim_index < len(claims)):
            continue
        edges.append(
            ClaimEdge(
                source_claim_id=claims[extracted.source_claim_index].id,
                target_claim_id=claims[extracted.target_claim_index].id,
                relation=EdgeRelation(extracted.relation),
                rationale=extracted.rationale,
                confidence=extracted.confidence,
            )
        )
    db.add_all(edges)
    db.commit()
    for e in edges:
        db.refresh(e)
    return edges


def ground_claims_step(db: Session, encounter: Encounter) -> list[GroundingCitation]:
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    if not claims:
        return []

    already_grounded = {
        row[0]
        for row in db.query(GroundingCitation.claim_id)
        .filter(GroundingCitation.claim_id.in_([c.id for c in claims]))
        .all()
    }
    to_ground = [c for c in claims if c.id not in already_grounded]
    if not to_ground:
        return (
            db.query(GroundingCitation)
            .filter(GroundingCitation.claim_id.in_([c.id for c in claims]))
            .all()
        )

    citations: list[GroundingCitation] = []
    for claim in to_ground:
        for chunk, score in retrieve_clinical_knowledge(db, claim.text, top_k=_GROUNDING_TOP_K):
            source_type = (
                GroundingSourceType.drug_data
                if chunk.category == "drug_interaction"
                else GroundingSourceType.guideline
            )
            citations.append(
                GroundingCitation(
                    claim_id=claim.id,
                    source_type=source_type,
                    source_identifier=chunk.source_identifier,
                    excerpt=chunk.content,
                    relevance_score=score,
                )
            )
        for chunk, score in retrieve_patient_history(db, encounter.patient_id, claim.text, top_k=_GROUNDING_TOP_K):
            citations.append(
                GroundingCitation(
                    claim_id=claim.id,
                    source_type=GroundingSourceType.prior_encounter,
                    source_identifier=chunk.source_encounter_label,
                    excerpt=chunk.content,
                    relevance_score=score,
                )
            )
    db.add_all(citations)
    db.commit()
    for c in citations:
        db.refresh(c)
    return citations


def run_policy_engine_step(db: Session, encounter: Encounter) -> list[PolicyVerdict]:
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    claim_ids = [c.id for c in claims]

    existing = (
        db.query(PolicyVerdict).filter(PolicyVerdict.claim_id.in_(claim_ids)).all() if claim_ids else []
    )
    if existing:
        return existing

    all_verdicts: list[PolicyVerdict] = []
    for claim in claims:
        all_verdicts.extend(run_policy_engine_for_claim(db, claim))
    db.commit()
    for v in all_verdicts:
        db.refresh(v)
    return all_verdicts
