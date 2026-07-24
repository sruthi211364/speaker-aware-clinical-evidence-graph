from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter, MockEhrSubmission, SoapNote
from app.models.enums import NoteStatus
from app.schemas.soap_note import MockEhrSubmissionRead
from app.services.fhir_export import build_fhir_bundle, record_ehr_submission

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["fhir-export"],
    dependencies=[Depends(require_auth)],
)


@router.post("/notes/{note_id}/export-fhir", response_model=MockEhrSubmissionRead, status_code=201)
def export_note_to_fhir(
    note_id: str,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Builds a FHIR R4B bundle (Composition + Observation/Condition per
    line + a DocumentReference wrapping the Composition) from a signed note
    and hands it to the mock EHR receiving endpoint. Only signed notes can
    be exported -- exporting a draft would mean an external system receives
    a record nobody has actually attested to."""
    try:
        note = db.get(SoapNote, note_id)
    except ValueError:
        note = None
    if note is None or note.encounter_id != encounter.id:
        raise HTTPException(status_code=404, detail="SOAP note not found on this encounter")
    if note.status != NoteStatus.signed:
        raise HTTPException(status_code=409, detail="Only a signed note can be exported to FHIR")

    claim_ids = {link.claim_id for line in note.lines for link in line.claim_links}
    claims_by_id = {c.id: c for c in db.query(Claim).filter(Claim.id.in_(claim_ids)).all()} if claim_ids else {}

    bundle = build_fhir_bundle(note, encounter, claims_by_id)
    submission = record_ehr_submission(db, encounter, note, bundle)
    return submission


@router.get("/ehr-submissions", response_model=list[MockEhrSubmissionRead])
def list_ehr_submissions(encounter: Encounter = Depends(get_encounter_or_404), db: Session = Depends(get_db)):
    """Every FHIR bundle handed to the mock EHR for this encounter, oldest
    first -- part of the audit/lineage view alongside the attestation trail
    and the LangGraph pipeline trace."""
    return (
        db.query(MockEhrSubmission)
        .filter_by(encounter_id=encounter.id)
        .order_by(MockEhrSubmission.received_at)
        .all()
    )
