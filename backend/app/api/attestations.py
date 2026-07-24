from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Attestation, Encounter
from app.schemas.soap_note import AttestationRead

router = APIRouter(
    prefix="/encounters/{encounter_id}/attestations",
    tags=["attestations"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[AttestationRead])
def list_attestations(encounter: Encounter = Depends(get_encounter_or_404), db: Session = Depends(get_db)):
    """The full clinician action trail for this encounter -- every accept,
    edit, and reject, in order. Sits alongside the LangGraph pipeline trace
    (.../pipeline/trace) as the other half of the audit view: this is the
    human decisions, that is the machine steps."""
    return (
        db.query(Attestation)
        .filter_by(encounter_id=encounter.id)
        .order_by(Attestation.created_at)
        .all()
    )
