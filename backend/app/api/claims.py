from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter
from app.models.enums import ClaimStatus, SourceType
from app.pipeline.steps import extract_claims_step
from app.schemas.claim import ClaimRead, EhrContextIngestRequest
from app.services.claude_service import ClaudeNotConfiguredError

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["claims"],
    dependencies=[Depends(require_auth)],
)


@router.post("/claims/extract", response_model=list[ClaimRead], status_code=201)
def extract_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Runs Claude-backed structured claim extraction over this encounter's
    transcript. Idempotent per encounter: if speech-derived claims already
    exist, returns them instead of extracting (and duplicating) again."""
    try:
        return extract_claims_step(db, encounter)
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/claims", response_model=list[ClaimRead])
def list_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    return (
        db.query(Claim)
        .filter_by(encounter_id=encounter.id)
        .order_by(Claim.created_at)
        .all()
    )


@router.post("/ehr-context", response_model=list[ClaimRead], status_code=201)
def ingest_ehr_context(
    payload: EhrContextIngestRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Mock EHR context (existing conditions, medications, allergies) is
    already structured data, so it becomes claims directly -- no Claude call
    needed, unlike free-text transcript segments."""
    claims = [
        Claim(
            encounter_id=encounter.id,
            text=item.text,
            claim_type=item.claim_type,
            source_type=SourceType.ehr_data,
            source_reference=item.record_id,
            confidence=1.0,
            status=ClaimStatus.proposed,
        )
        for item in payload.items
    ]
    db.add_all(claims)
    db.commit()
    for c in claims:
        db.refresh(c)
    return claims
