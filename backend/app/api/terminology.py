from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Encounter
from app.pipeline.steps import normalize_terminology_step
from app.schemas.claim import ClaimRead

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["terminology"],
    dependencies=[Depends(require_auth)],
)


@router.post("/claims/normalize", response_model=list[ClaimRead], status_code=201)
def normalize_terminology(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Maps each surviving claim's clinical concept to a RxNorm (medication),
    SNOMED CT (condition/finding), or LOINC (observation/vital) code via
    embedding search over a curated vocabulary index. Only claims that
    haven't been coded yet are processed, so this is safe to re-run after
    new claims are added (e.g. from an answered clarification)."""
    return normalize_terminology_step(db, encounter)
