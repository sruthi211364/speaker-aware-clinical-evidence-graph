from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Encounter


def get_encounter_or_404(encounter_id: str, db: Session = Depends(get_db)) -> Encounter:
    try:
        encounter = db.get(Encounter, encounter_id)
    except ValueError:
        encounter = None
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return encounter
