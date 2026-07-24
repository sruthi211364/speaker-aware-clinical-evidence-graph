from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter, GroundingCitation
from app.models.enums import GroundingSourceType
from app.schemas.grounding import GroundingCitationRead
from app.services.retrieval_service import retrieve_clinical_knowledge, retrieve_patient_history

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["grounding"],
    dependencies=[Depends(require_auth)],
)

_TOP_K = 2


@router.post("/claims/ground", response_model=list[GroundingCitationRead], status_code=201)
def ground_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Retrieves clinical knowledge and patient history evidence for each of
    this encounter's claims and stores it as grounding citations. Idempotent
    per encounter: skips claims that already have citations."""
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

    try:
        citations: list[GroundingCitation] = []
        for claim in to_ground:
            for chunk, score in retrieve_clinical_knowledge(db, claim.text, top_k=_TOP_K):
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
            for chunk, score in retrieve_patient_history(db, encounter.patient_id, claim.text, top_k=_TOP_K):
                citations.append(
                    GroundingCitation(
                        claim_id=claim.id,
                        source_type=GroundingSourceType.prior_encounter,
                        source_identifier=chunk.source_encounter_label,
                        excerpt=chunk.content,
                        relevance_score=score,
                    )
                )
    except Exception as exc:  # embedding model load / inference failure
        raise HTTPException(status_code=503, detail=f"Grounding retrieval failed: {exc}")

    db.add_all(citations)
    db.commit()
    for c in citations:
        db.refresh(c)
    return citations


@router.get("/claims/{claim_id}/citations", response_model=list[GroundingCitationRead])
def get_claim_citations(
    claim_id: str,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    try:
        claim = db.get(Claim, claim_id)
    except ValueError:
        claim = None
    if claim is None or claim.encounter_id != encounter.id:
        raise HTTPException(status_code=404, detail="Claim not found on this encounter")
    return (
        db.query(GroundingCitation)
        .filter_by(claim_id=claim.id)
        .order_by(GroundingCitation.relevance_score.desc())
        .all()
    )
