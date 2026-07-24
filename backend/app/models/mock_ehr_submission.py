import datetime as dt

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID, new_uuid


class MockEhrSubmission(Base):
    """A record of one FHIR bundle handed off to the mock EHR receiving
    endpoint. Stands in for a real EHR integration -- see README deviations.
    The full bundle is kept verbatim so the export can be inspected or
    replayed without recomputing it from the (possibly since-amended) note.
    """

    __tablename__ = "mock_ehr_submissions"

    id: Mapped[GUID] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    encounter_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("encounters.id"))
    note_id: Mapped[GUID] = mapped_column(GUID(), ForeignKey("soap_notes.id"))
    bundle: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
