"""Seeds three demo encounters spanning the system's main features (plus the
RAG knowledge base and vocabulary index via seed_knowledge/seed_vocabulary),
so the system is explorable immediately after setup without needing a
funded Anthropic API key.

Claim extraction and edge generation are the only pipeline steps that
genuinely require a live Claude call -- this script bypasses just those two
with realistic, hand-authored claims/edges (clearly seed data, not a claim
of real model output). Every other step (RAG grounding, terminology
normalization, SOAP compilation, FHIR export) is exercised via the real
application code in app/pipeline/steps.py and app/services/fhir_export.py,
not reimplemented here, so the seeded state is exactly what those code
paths actually produce.

Usage: python -m app.seed
"""

import datetime as dt

from app.db import SessionLocal
from app.models import (
    Attestation,
    Claim,
    ClaimEdge,
    ClarificationQuestion,
    Encounter,
    PolicyVerdict,
    TranscriptSegment,
    User,
)
from app.models.enums import (
    AttestationAction,
    ClaimStatus,
    ClaimType,
    EdgeRelation,
    EncounterStatus,
    NoteStatus,
    PolicyCheckType,
    SourceType,
    SpeakerRole,
)
from app.pipeline.steps import compile_soap_note_step, ground_claims_step, normalize_terminology_step
from app.seed_knowledge import run as seed_knowledge
from app.seed_vocabulary import run as seed_vocabulary
from app.services.fhir_export import build_fhir_bundle, record_ehr_submission


def _add_verdicts(
    db,
    claim: Claim,
    *,
    contradiction: bool = True,
    temporal: bool = True,
    missing_context: bool = True,
    safety: bool = True,
    contradiction_rationale: str | None = None,
    missing_context_rationale: str | None = None,
    safety_rationale: str | None = None,
) -> list[PolicyVerdict]:
    """Creates the 5 policy verdicts for a claim and sets its status using
    the same precedence the real policy engine applies (safety >
    contradiction > missing_context > ambiguous > supported) -- see
    app/services/policy_engine.py. Stands in for that engine's
    Claude-assisted checks with hand-authored, realistic verdicts; the
    support check is real (every seeded claim below carries an actual
    source_reference)."""
    verdicts = [
        PolicyVerdict(claim_id=claim.id, check_type=PolicyCheckType.support, passed=True, rationale=None),
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.contradiction,
            passed=contradiction,
            rationale=contradiction_rationale,
        ),
        PolicyVerdict(claim_id=claim.id, check_type=PolicyCheckType.temporal_ambiguity, passed=temporal, rationale=None),
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.missing_context,
            passed=missing_context,
            rationale=missing_context_rationale,
        ),
        PolicyVerdict(
            claim_id=claim.id, check_type=PolicyCheckType.clinical_safety, passed=safety, rationale=safety_rationale
        ),
    ]
    db.add_all(verdicts)
    if not safety:
        claim.status = ClaimStatus.unsafe
    elif not contradiction:
        claim.status = ClaimStatus.contradicted
    elif not missing_context:
        claim.status = ClaimStatus.missing_context
    elif not temporal:
        claim.status = ClaimStatus.ambiguous
    else:
        claim.status = ClaimStatus.supported
    return verdicts


def seed_contradiction_encounter(db, clinician: User, patient: User) -> Encounter:
    """Scenario 1: a patient/caregiver timeline contradiction, left
    mid-review (compiled, under_review, unsigned) so a reviewer can
    practice the accept/edit/reject/sign workflow themselves."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.reviewed)
    db.add(encounter)
    db.flush()

    segments_data = [
        (SpeakerRole.clinician, "clinician-1", 0, 4000, "What brings you in today?"),
        (
            SpeakerRole.patient,
            "patient-1",
            4200,
            9500,
            "I've had this chest pain for about three days now, it's a dull ache.",
        ),
        (
            SpeakerRole.caregiver,
            "caregiver-1",
            9700,
            14000,
            "Actually I think it's been going on since last week, he mentioned it at dinner.",
        ),
        (SpeakerRole.clinician, "clinician-1", 14200, 17000, "Any shortness of breath or radiation to your arm?"),
        (SpeakerRole.patient, "patient-1", 17200, 20000, "No shortness of breath. It doesn't really move anywhere else."),
    ]
    segments = []
    for role, speaker_id, start_ms, end_ms, text in segments_data:
        seg = TranscriptSegment(
            encounter_id=encounter.id,
            speaker_role=role,
            speaker_identifier=speaker_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            confidence=0.95,
        )
        db.add(seg)
        segments.append(seg)
    db.flush()

    patient_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports chest pain for about three days, described as a dull ache",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[1].id),
        confidence=0.92,
        status=ClaimStatus.proposed,
    )
    caregiver_claim = Claim(
        encounter_id=encounter.id,
        text="caregiver reports the chest pain has been going on since last week",
        claim_type=ClaimType.symptom,
        source_type=SourceType.caregiver_report,
        source_reference=str(segments[2].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )
    no_dyspnea_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies shortness of breath",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[4].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    no_radiation_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies radiation of the chest pain",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[4].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    db.add_all([patient_claim, caregiver_claim, no_dyspnea_claim, no_radiation_claim])
    db.flush()

    db.add(
        ClaimEdge(
            source_claim_id=patient_claim.id,
            target_claim_id=caregiver_claim.id,
            relation=EdgeRelation.contradicts,
            rationale="Different onset timelines reported by patient (three days) vs. caregiver (since last week) for the same symptom.",
            confidence=0.87,
        )
    )
    db.flush()

    contradiction_rationale = "Conflicts with another claim from a different source in this encounter."
    _add_verdicts(db, patient_claim, contradiction=False, contradiction_rationale=contradiction_rationale)
    _add_verdicts(db, caregiver_claim, contradiction=False, contradiction_rationale=contradiction_rationale)
    _add_verdicts(db, no_dyspnea_claim)
    _add_verdicts(db, no_radiation_claim)
    db.commit()

    ground_claims_step(db, encounter)
    normalize_terminology_step(db, encounter)
    note = compile_soap_note_step(db, encounter)
    note.status = NoteStatus.under_review
    db.commit()
    return encounter


def seed_safety_flag_encounter(db, clinician: User, patient: User) -> Encounter:
    """Scenario 2: a clinical safety flag (prescribing amoxicillin despite a
    documented penicillin allergy), taken all the way through signing and
    FHIR export so a reviewer can see the full lifecycle without doing
    anything themselves."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.in_progress)
    db.add(encounter)
    db.flush()

    segments_data = [
        (SpeakerRole.clinician, "clinician-1", 0, 3000, "Let's get you started on an antibiotic for that sinus infection."),
        (SpeakerRole.patient, "patient-1", 3200, 6000, "Okay, whatever you think is best."),
        (SpeakerRole.patient, "patient-1", 6200, 10000, "My seasonal allergies have been fine lately, the loratadine handles it."),
    ]
    segments = []
    for role, speaker_id, start_ms, end_ms, text in segments_data:
        seg = TranscriptSegment(
            encounter_id=encounter.id,
            speaker_role=role,
            speaker_identifier=speaker_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            confidence=0.95,
        )
        db.add(seg)
        segments.append(seg)
    db.flush()

    allergy_claim = Claim(
        encounter_id=encounter.id,
        text="documented penicillin allergy",
        claim_type=ClaimType.allergy,
        source_type=SourceType.ehr_data,
        source_reference="ehr-allergy-1",
        confidence=1.0,
        status=ClaimStatus.proposed,
    )
    prescription_claim = Claim(
        encounter_id=encounter.id,
        text="clinician prescribes amoxicillin 500mg three times daily",
        claim_type=ClaimType.medication,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[0].id),
        confidence=0.93,
        status=ClaimStatus.proposed,
    )
    seasonal_allergy_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports seasonal allergies, well controlled with loratadine",
        claim_type=ClaimType.allergy,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[2].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    db.add_all([allergy_claim, prescription_claim, seasonal_allergy_claim])
    db.flush()

    _add_verdicts(db, allergy_claim)
    _add_verdicts(
        db,
        prescription_claim,
        safety=False,
        safety_rationale=(
            "Amoxicillin is a penicillin-class antibiotic and this patient has a documented penicillin "
            "allergy; cross-reactivity risk applies to related beta-lactams as well."
        ),
    )
    _add_verdicts(db, seasonal_allergy_claim)
    db.commit()

    ground_claims_step(db, encounter)
    normalize_terminology_step(db, encounter)
    note = compile_soap_note_step(db, encounter)

    note.status = NoteStatus.signed
    note.signed_by = clinician.id
    note.signed_at = dt.datetime.utcnow()
    encounter.status = EncounterStatus.signed
    db.add(
        Attestation(
            encounter_id=encounter.id,
            note_version_id=note.id,
            actor_id=clinician.id,
            action=AttestationAction.signed,
            before_value=None,
            after_value=f"Signed note version {note.version}",
        )
    )
    db.commit()
    db.refresh(note)

    claim_ids = {link.claim_id for line in note.lines for link in line.claim_links}
    claims_by_id = {c.id: c for c in db.query(Claim).filter(Claim.id.in_(claim_ids)).all()} if claim_ids else {}
    bundle = build_fhir_bundle(note, encounter, claims_by_id)
    record_ehr_submission(db, encounter, note, bundle)
    return encounter


def seed_missing_context_encounter(db, clinician: User, patient: User) -> Encounter:
    """Scenario 3: a vague symptom report that trips the missing-context
    check, left with its clarification question unresolved -- shows the
    Clarifications tab in action and the sign gate that blocks on it."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.in_progress)
    db.add(encounter)
    db.flush()

    seg = TranscriptSegment(
        encounter_id=encounter.id,
        speaker_role=SpeakerRole.patient,
        speaker_identifier="patient-1",
        start_ms=0,
        end_ms=3000,
        text="I've just been feeling really tired lately.",
        confidence=0.93,
    )
    db.add(seg)
    db.flush()

    fatigue_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports fatigue",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(seg.id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    db.add(fatigue_claim)
    db.flush()

    missing_context_rationale = "Duration and severity of the fatigue are not documented."
    _add_verdicts(db, fatigue_claim, missing_context=False, missing_context_rationale=missing_context_rationale)
    db.commit()

    ground_claims_step(db, encounter)
    normalize_terminology_step(db, encounter)

    db.add(
        ClarificationQuestion(
            encounter_id=encounter.id,
            triggering_claim_id=fatigue_claim.id,
            question_text="How long has the fatigue lasted, and how severe would you say it is?",
            grounding_citation_id=None,
        )
    )
    db.commit()

    compile_soap_note_step(db, encounter)
    return encounter


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

        e1 = seed_contradiction_encounter(db, clinician, patient)
        e2 = seed_safety_flag_encounter(db, clinician, patient)
        e3 = seed_missing_context_encounter(db, clinician, patient)
        print(
            f"Seeded 3 demo encounters: contradiction (mid-review) {e1.id}, "
            f"safety flag (signed + exported) {e2.id}, missing context (unresolved) {e3.id}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
    seed_knowledge()
    seed_vocabulary()
