from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404, get_or_create_demo_user
from app.auth import require_auth
from app.db import get_db
from app.models import Attestation, Claim, Encounter, SoapNote, SoapNoteLine
from app.models.enums import AttestationAction, ClaimStatus, NoteStatus
from app.pipeline.steps import compile_soap_note_step
from app.schemas.soap_note import AttestationRead, SoapNoteLineEditRequest, SoapNoteRead

router = APIRouter(
    prefix="/encounters/{encounter_id}/notes",
    tags=["soap-notes"],
    dependencies=[Depends(require_auth)],
)


def _get_note_or_404(encounter: Encounter, note_id: str, db: Session) -> SoapNote:
    try:
        note = db.get(SoapNote, note_id)
    except ValueError:
        note = None
    if note is None or note.encounter_id != encounter.id:
        raise HTTPException(status_code=404, detail="SOAP note not found on this encounter")
    return note


def _get_line_or_404(note: SoapNote, line_id: str, db: Session) -> SoapNoteLine:
    try:
        line = db.get(SoapNoteLine, line_id)
    except ValueError:
        line = None
    if line is None or line.note_id != note.id:
        raise HTTPException(status_code=404, detail="Note line not found on this note")
    return line


def _write_attestation(
    db: Session,
    encounter: Encounter,
    note: SoapNote,
    line: SoapNoteLine,
    action: AttestationAction,
    before_value: str | None,
    after_value: str | None,
) -> Attestation:
    actor = get_or_create_demo_user(db, "clinician")
    attestation = Attestation(
        encounter_id=encounter.id,
        note_version_id=note.id,
        note_line_id=line.id,
        claim_id=line.claim_links[0].claim_id if line.claim_links else None,
        actor_id=actor.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
    )
    db.add(attestation)
    db.commit()
    db.refresh(attestation)
    return attestation


@router.post("/compile", response_model=SoapNoteRead, status_code=201)
def compile_note(encounter: Encounter = Depends(get_encounter_or_404), db: Session = Depends(get_db)):
    """Compiles the current surviving claims into a SOAP note. Idempotent
    per encounter -- if a note already exists, returns it unchanged rather
    than regenerating it (see compile_soap_note_step)."""
    note = compile_soap_note_step(db, encounter)
    return SoapNoteRead.from_note(note)


@router.get("/latest", response_model=SoapNoteRead)
def get_latest_note(encounter: Encounter = Depends(get_encounter_or_404), db: Session = Depends(get_db)):
    note = (
        db.query(SoapNote)
        .filter_by(encounter_id=encounter.id)
        .order_by(SoapNote.version.desc())
        .first()
    )
    if note is None:
        raise HTTPException(status_code=404, detail="No SOAP note compiled yet for this encounter")
    return SoapNoteRead.from_note(note)


@router.get("", response_model=list[SoapNoteRead])
def list_notes(encounter: Encounter = Depends(get_encounter_or_404), db: Session = Depends(get_db)):
    notes = db.query(SoapNote).filter_by(encounter_id=encounter.id).order_by(SoapNote.version).all()
    return [SoapNoteRead.from_note(n) for n in notes]


@router.post("/{note_id}/lines/{line_id}/accept", response_model=AttestationRead, status_code=201)
def accept_line(
    note_id: str,
    line_id: str,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    note = _get_note_or_404(encounter, note_id, db)
    line = _get_line_or_404(note, line_id, db)
    return _write_attestation(db, encounter, note, line, AttestationAction.accepted, line.text, line.text)


@router.post("/{note_id}/lines/{line_id}/edit", response_model=AttestationRead, status_code=201)
def edit_line(
    note_id: str,
    line_id: str,
    payload: SoapNoteLineEditRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    note = _get_note_or_404(encounter, note_id, db)
    if note.status == NoteStatus.signed:
        raise HTTPException(status_code=409, detail="Cannot edit a line on a signed note")
    line = _get_line_or_404(note, line_id, db)
    before = line.text
    line.text = payload.text
    db.flush()
    return _write_attestation(db, encounter, note, line, AttestationAction.edited, before, payload.text)


@router.post("/{note_id}/lines/{line_id}/reject", response_model=AttestationRead, status_code=201)
def reject_line(
    note_id: str,
    line_id: str,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Rejecting a line keeps it in the note (never silently deleted -- the
    attestation already captured why) but flags it so the UI can grey it out
    instead of presenting it as part of the record.

    For a single-claim line, the underlying claim's status is also set to
    "rejected" so it's excluded if the note is ever recompiled. A conflict
    line cites two claims, and rejecting the merged statement doesn't cleanly
    mean either individual claim was wrong -- so claim status is left alone
    there; only the line itself is flagged."""
    note = _get_note_or_404(encounter, note_id, db)
    if note.status == NoteStatus.signed:
        raise HTTPException(status_code=409, detail="Cannot reject a line on a signed note")
    line = _get_line_or_404(note, line_id, db)
    before = line.text
    line.is_rejected = True
    if len(line.claim_links) == 1:
        claim = db.get(Claim, line.claim_links[0].claim_id)
        if claim is not None:
            claim.status = ClaimStatus.rejected
    db.flush()
    return _write_attestation(db, encounter, note, line, AttestationAction.rejected, before, None)
