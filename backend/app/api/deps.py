from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Encounter, User


def get_encounter_or_404(encounter_id: str, db: Session = Depends(get_db)) -> Encounter:
    try:
        encounter = db.get(Encounter, encounter_id)
    except ValueError:
        encounter = None
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return encounter


def get_or_create_demo_user(db: Session, role: str) -> User:
    """There's no real auth/user system yet, so review actions (accept/edit/
    reject) are attributed to a stable demo user per role rather than a
    signed-in clinician."""
    email = f"demo.{role}@example.com"
    user = db.query(User).filter_by(email=email).first()
    if user:
        return user
    user = User(display_name=f"Demo {role.capitalize()}", role=role, email=email)
    db.add(user)
    db.flush()
    return user
