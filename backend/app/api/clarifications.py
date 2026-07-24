import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, ClarificationQuestion, Encounter
from app.models.enums import ClaimStatus, ClaimType, SourceType
from app.schemas.policy import ClarificationAnswerRequest, ClarificationQuestionRead

router = APIRouter(
    prefix="/encounters/{encounter_id}/clarifications",
    tags=["clarifications"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[ClarificationQuestionRead])
def list_clarifications(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    return (
        db.query(ClarificationQuestion)
        .filter_by(encounter_id=encounter.id)
        .order_by(ClarificationQuestion.created_at)
        .all()
    )


@router.post("/{clarification_id}/answer", response_model=ClarificationQuestionRead)
def answer_clarification(
    clarification_id: str,
    payload: ClarificationAnswerRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Answering a clarification creates a new claim with source_type
    clinician_judgment -- the gap is filled by an explicit clinician
    statement, never a model-generated guess."""
    try:
        clarification = db.get(ClarificationQuestion, clarification_id)
    except ValueError:
        clarification = None
    if clarification is None or clarification.encounter_id != encounter.id:
        raise HTTPException(status_code=404, detail="Clarification question not found on this encounter")
    if clarification.resolved:
        raise HTTPException(status_code=409, detail="Clarification question already resolved")

    triggering_claim = db.get(Claim, clarification.triggering_claim_id)

    answer_claim = Claim(
        encounter_id=encounter.id,
        text=payload.answer_text,
        claim_type=triggering_claim.claim_type if triggering_claim else ClaimType.other,
        source_type=SourceType.clinician_judgment,
        source_reference=str(clarification.id),
        confidence=1.0,
        status=ClaimStatus.proposed,
    )
    db.add(answer_claim)
    db.flush()

    clarification.resolved = True
    clarification.resolved_by_claim_id = answer_claim.id
    clarification.resolved_at = dt.datetime.utcnow()

    db.commit()
    db.refresh(clarification)
    return clarification
