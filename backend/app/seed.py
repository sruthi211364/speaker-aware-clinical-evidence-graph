"""Seeds a small demo encounter so the system is explorable immediately after
setup. Extended in later phases as claims, notes, and citations come online.

Usage: python -m app.seed
"""

from app.db import SessionLocal
from app.models import Encounter, TranscriptSegment, User
from app.models.enums import SpeakerRole


def run() -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(email="demo.clinician@example.com").first()
        if existing:
            print("Seed data already present, skipping.")
            return

        clinician = User(display_name="Dr. Amara Diallo", role="clinician", email="demo.clinician@example.com")
        patient = User(display_name="Jordan Reyes", role="patient", email="demo.patient@example.com")
        db.add_all([clinician, patient])
        db.flush()

        encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id)
        db.add(encounter)
        db.flush()

        # A deliberately contradictory onset timeline between patient and
        # caregiver -- this is the seam Phase 3's graph construction and
        # Phase 5's policy engine are built to surface, not blend away.
        segments = [
            (SpeakerRole.clinician, "clinician-1", 0, 4000,
             "What brings you in today?"),
            (SpeakerRole.patient, "patient-1", 4200, 9500,
             "I've had this chest pain for about three days now, it's a dull ache."),
            (SpeakerRole.caregiver, "caregiver-1", 9700, 14000,
             "Actually I think it's been going on since last week, he mentioned it at dinner."),
            (SpeakerRole.clinician, "clinician-1", 14200, 17000,
             "Any shortness of breath or radiation to your arm?"),
            (SpeakerRole.patient, "patient-1", 17200, 20000,
             "No shortness of breath. It doesn't really move anywhere else."),
        ]

        for i, (role, speaker_id, start_ms, end_ms, text) in enumerate(segments):
            db.add(
                TranscriptSegment(
                    encounter_id=encounter.id,
                    speaker_role=role,
                    speaker_identifier=speaker_id,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    confidence=0.95,
                )
            )

        db.commit()
        print(f"Seeded encounter {encounter.id} with {len(segments)} transcript segments.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
