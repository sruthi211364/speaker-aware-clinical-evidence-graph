from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404, get_or_create_demo_user
from app.auth import require_auth
from app.db import get_db
from app.models import Encounter
from app.schemas.encounter import EncounterCreate, EncounterRead

router = APIRouter(prefix="/encounters", tags=["encounters"], dependencies=[Depends(require_auth)])


@router.post("", response_model=EncounterRead, status_code=201)
def create_encounter(payload: EncounterCreate, db: Session = Depends(get_db)):
    patient_id = payload.patient_id or get_or_create_demo_user(db, "patient").id
    clinician_id = payload.clinician_id or get_or_create_demo_user(db, "clinician").id

    encounter = Encounter(patient_id=patient_id, clinician_id=clinician_id)
    db.add(encounter)
    db.commit()
    db.refresh(encounter)
    return encounter


@router.get("", response_model=list[EncounterRead])
def list_encounters(db: Session = Depends(get_db)):
    return db.query(Encounter).order_by(Encounter.started_at.desc()).all()


@router.get("/{encounter_id}", response_model=EncounterRead)
def get_encounter(encounter: Encounter = Depends(get_encounter_or_404)):
    return encounter
