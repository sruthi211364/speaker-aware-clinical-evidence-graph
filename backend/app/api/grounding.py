from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter, GroundingCitation
from app.pipeline.steps import ground_claims_step
from app.schemas.grounding import GroundingCitationRead

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["grounding"],
    dependencies=[Depends(require_auth)],
)


@router.post("/claims/ground", response_model=list[GroundingCitationRead], status_code=201)
def ground_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Retrieves clinical knowledge and patient history evidence for each of
    this encounter's claims and stores it as grounding citations. Idempotent
    per encounter: skips claims that already have citations."""
    try:
        return ground_claims_step(db, encounter)
    except Exception as exc:  # embedding model load / inference failure
        raise HTTPException(status_code=503, detail=f"Grounding retrieval failed: {exc}")


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
