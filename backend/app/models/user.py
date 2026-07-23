import datetime as dt

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID, new_uuid


class User(Base):
    """A minimal identity record for patients, clinicians, and caregivers
    referenced by encounters, claims, and attestations. Real auth/RBAC is out
    of scope for this prototype -- see SECURITY.md."""

    __tablename__ = "users"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))  # patient | clinician | caregiver
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
