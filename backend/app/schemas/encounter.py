import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EncounterStatus


class EncounterCreate(BaseModel):
    # Optional: if omitted, a default demo patient/clinician is used so the
    # frontend can create an encounter with zero required input.
    patient_id: uuid.UUID | None = None
    clinician_id: uuid.UUID | None = None


class EncounterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    clinician_id: uuid.UUID
    started_at: dt.datetime
    ended_at: dt.datetime | None
    status: EncounterStatus
    created_at: dt.datetime
    updated_at: dt.datetime
