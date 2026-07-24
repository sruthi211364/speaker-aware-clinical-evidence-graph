from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter, PolicyVerdict
from app.pipeline.steps import run_policy_engine_step
from app.schemas.policy import PolicyVerdictRead
from app.services.claude_service import ClaudeNotConfiguredError

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["policy"],
    dependencies=[Depends(require_auth)],
)


@router.post("/claims/policy-check", response_model=list[PolicyVerdictRead], status_code=201)
def run_policy_check(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Runs the five-part zero-trust policy engine over every claim in this
    encounter: support (rule), contradiction (rule + Claude-assisted vs.
    longitudinal history), temporal ambiguity, missing context, and clinical
    safety (all Claude-assisted, grounded in Phase 4's retrieved evidence).
    Idempotent per encounter. Requires claims to already be grounded --
    run .../claims/ground first (or use POST .../pipeline/run for the full
    orchestrated pipeline)."""
    try:
        return run_policy_engine_step(db, encounter)
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/policy-verdicts", response_model=list[PolicyVerdictRead])
def list_policy_verdicts(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    claim_ids = [c.id for c in db.query(Claim.id).filter_by(encounter_id=encounter.id).all()]
    if not claim_ids:
        return []
    return (
        db.query(PolicyVerdict)
        .filter(PolicyVerdict.claim_id.in_(claim_ids))
        .order_by(PolicyVerdict.created_at)
        .all()
    )
