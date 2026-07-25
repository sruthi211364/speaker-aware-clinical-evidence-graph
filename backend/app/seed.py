"""Seeds three demo encounters spanning the system's main features (plus the
RAG knowledge base and vocabulary index via seed_knowledge/seed_vocabulary),
so the system is explorable immediately after setup without needing a
funded Anthropic API key.

The transcripts are written as full, conversational encounters -- greeting,
history of present illness, review of systems, exam, assessment, plan --
not just the one sentence that trips the interesting scenario, because a
demo that only ever shows the punchline doesn't look like a real visit.

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


def _add_segments(db, encounter: Encounter, lines: list[tuple]) -> list[TranscriptSegment]:
    """lines is a list of (speaker_role, speaker_identifier, start_ms, end_ms, text)."""
    segments = []
    for role, speaker_id, start_ms, end_ms, text in lines:
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
    return segments


def seed_contradiction_encounter(db, clinician: User, patient: User) -> Encounter:
    """Scenario 1: a full chest-pain workup -- history, review of systems,
    exam, assessment, and plan -- with a patient/caregiver timeline
    contradiction buried in the middle of it, the way it actually comes up
    in a real visit. Left mid-review (compiled, under_review, unsigned) so
    a reviewer can practice the accept/edit/reject/sign workflow
    themselves."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.reviewed)
    db.add(encounter)
    db.flush()

    segments = _add_segments(
        db,
        encounter,
        [
            (SpeakerRole.clinician, "clinician-1", 0, 3000, "Good morning. What brings you in to see us today?"),
            (SpeakerRole.patient, "patient-1", 3200, 7500, "Hi, um, I've been having this chest pain and it's kind of freaking me out."),
            (SpeakerRole.clinician, "clinician-1", 7700, 10500, "Okay, let's talk through it. When did it start?"),
            (SpeakerRole.patient, "patient-1", 10700, 15500, "I want to say... about three days ago. It's been a dull ache, comes and goes."),
            (SpeakerRole.caregiver, "caregiver-1", 15700, 22500, "Actually, I think it's been longer than that. He mentioned it to me at dinner last week, so I'd say more like since last week."),
            (SpeakerRole.clinician, "clinician-1", 22700, 27000, "Okay, good to know, we'll keep both timelines in mind. Can you point to where exactly it hurts?"),
            (SpeakerRole.patient, "patient-1", 27200, 31000, "Right in the center of my chest, kind of behind the breastbone."),
            (SpeakerRole.clinician, "clinician-1", 31200, 34500, "On a scale of one to ten, how bad is it when it's at its worst?"),
            (SpeakerRole.patient, "patient-1", 34700, 38500, "Maybe a four or five. It's not unbearable, just uncomfortable."),
            (SpeakerRole.clinician, "clinician-1", 38700, 42000, "Does it move anywhere else, like your arm, jaw, or back?"),
            (SpeakerRole.patient, "patient-1", 42200, 44800, "No, it stays pretty much in one spot."),
            (SpeakerRole.clinician, "clinician-1", 45000, 47500, "Any shortness of breath with it?"),
            (SpeakerRole.patient, "patient-1", 47700, 49800, "No, breathing's been fine."),
            (SpeakerRole.clinician, "clinician-1", 50000, 53000, "What about nausea, sweating, or your heart racing?"),
            (SpeakerRole.patient, "patient-1", 53200, 55000, "No, none of that."),
            (SpeakerRole.clinician, "clinician-1", 55200, 59000, "Does anything make it better or worse -- exercise, eating, lying down?"),
            (SpeakerRole.patient, "patient-1", 59200, 63000, "Honestly I haven't noticed a pattern. It just comes and goes."),
            (SpeakerRole.clinician, "clinician-1", 63200, 67500, "Okay. Do you have any history of high blood pressure, diabetes, or heart problems?"),
            (SpeakerRole.patient, "patient-1", 67700, 72000, "I have high blood pressure. I've been on medication for a couple of years now."),
            (SpeakerRole.clinician, "clinician-1", 72200, 74000, "Which medication is that?"),
            (SpeakerRole.patient, "patient-1", 74200, 77000, "Lisinopril, ten milligrams, once a day."),
            (SpeakerRole.clinician, "clinician-1", 77200, 80500, "Good. Any allergies to medications that you know of?"),
            (SpeakerRole.patient, "patient-1", 80700, 82500, "Not that I know of."),
            (SpeakerRole.clinician, "clinician-1", 82700, 85500, "And any family history of heart disease?"),
            (SpeakerRole.patient, "patient-1", 85700, 89000, "My father actually had a heart attack in his fifties."),
            (SpeakerRole.clinician, "clinician-1", 89200, 93500, "Thanks, that's helpful context. Let me take a listen to your heart and lungs."),
            (SpeakerRole.clinician, "clinician-1", 93700, 99500, "Your heart sounds are regular, no murmurs, and your lungs are clear. You don't look like you're in any acute distress."),
            (SpeakerRole.clinician, "clinician-1", 99700, 102500, "Blood pressure today is 128 over 82."),
            (SpeakerRole.clinician, "clinician-1", 102700, 109000, "Given the story, I want to rule out a cardiac cause even though what I'm hearing and seeing today is reassuring."),
            (SpeakerRole.clinician, "clinician-1", 109200, 113500, "We'll get an EKG now, and I'd like to draw some blood work as well."),
            (SpeakerRole.clinician, "clinician-1", 113700, 121000, "Let's plan to follow up in about a week -- sooner if the pain changes, gets worse, or you develop any shortness of breath."),
        ],
    )

    patient_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports chest pain for about three days, described as a dull ache",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[3].id),
        confidence=0.92,
        status=ClaimStatus.proposed,
    )
    caregiver_claim = Claim(
        encounter_id=encounter.id,
        text="caregiver reports the chest pain has been going on since last week",
        claim_type=ClaimType.symptom,
        source_type=SourceType.caregiver_report,
        source_reference=str(segments[4].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )
    location_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports pain centrally located behind the breastbone",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[6].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    severity_claim = Claim(
        encounter_id=encounter.id,
        text="patient rates pain severity as four to five out of ten at its worst",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[8].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )
    no_radiation_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies radiation of the chest pain",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[10].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    no_dyspnea_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies shortness of breath",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[12].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    no_other_symptoms_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies nausea, diaphoresis, or palpitations",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[14].id),
        confidence=0.87,
        status=ClaimStatus.proposed,
    )
    hypertension_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports a history of hypertension, on medication for a couple of years",
        claim_type=ClaimType.history,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[18].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    lisinopril_claim = Claim(
        encounter_id=encounter.id,
        text="patient takes lisinopril 10mg once daily",
        claim_type=ClaimType.medication,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[20].id),
        confidence=0.92,
        status=ClaimStatus.proposed,
    )
    no_drug_allergy_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies known drug allergies",
        claim_type=ClaimType.allergy,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[22].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    family_history_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports family history of myocardial infarction in father, age of onset fifties",
        claim_type=ClaimType.history,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[24].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )
    exam_claim = Claim(
        encounter_id=encounter.id,
        text="heart sounds regular without murmurs, lungs clear, no acute distress",
        claim_type=ClaimType.exam_finding,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[26].id),
        confidence=0.93,
        status=ClaimStatus.proposed,
    )
    vital_claim = Claim(
        encounter_id=encounter.id,
        text="blood pressure 128/82",
        claim_type=ClaimType.vital,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[27].id),
        confidence=0.95,
        status=ClaimStatus.proposed,
    )
    assessment_claim = Claim(
        encounter_id=encounter.id,
        text="assessment: atypical chest pain, reassuring exam today, cardiac etiology to be ruled out",
        claim_type=ClaimType.assessment,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[28].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    ekg_claim = Claim(
        encounter_id=encounter.id,
        text="plan: obtain EKG",
        claim_type=ClaimType.plan_item,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[29].id),
        confidence=0.92,
        status=ClaimStatus.proposed,
    )
    labs_claim = Claim(
        encounter_id=encounter.id,
        text="plan: obtain blood work",
        claim_type=ClaimType.plan_item,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[29].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    followup_claim = Claim(
        encounter_id=encounter.id,
        text="plan: follow up in one week, sooner if pain worsens or shortness of breath develops",
        claim_type=ClaimType.plan_item,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[30].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )

    all_claims = [
        patient_claim,
        caregiver_claim,
        location_claim,
        severity_claim,
        no_radiation_claim,
        no_dyspnea_claim,
        no_other_symptoms_claim,
        hypertension_claim,
        lisinopril_claim,
        no_drug_allergy_claim,
        family_history_claim,
        exam_claim,
        vital_claim,
        assessment_claim,
        ekg_claim,
        labs_claim,
        followup_claim,
    ]
    db.add_all(all_claims)
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
    for claim in all_claims[2:]:
        _add_verdicts(db, claim)
    db.commit()

    ground_claims_step(db, encounter)
    normalize_terminology_step(db, encounter)
    note = compile_soap_note_step(db, encounter)
    note.status = NoteStatus.under_review
    db.commit()
    return encounter


def seed_safety_flag_encounter(db, clinician: User, patient: User) -> Encounter:
    """Scenario 2: a sinus infection visit -- history, a documented allergy
    that never comes up out loud (the exact way a chart-review miss
    actually happens), exam, and a prescription that conflicts with it.
    Taken all the way through signing and FHIR export so a reviewer can
    see the full lifecycle without doing anything themselves."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.in_progress)
    db.add(encounter)
    db.flush()

    segments = _add_segments(
        db,
        encounter,
        [
            (SpeakerRole.clinician, "clinician-1", 0, 2500, "Hi there, what's going on today?"),
            (SpeakerRole.patient, "patient-1", 2700, 8000, "My sinuses have been awful for about a week now. Lots of pressure in my face and thick, gross drainage."),
            (SpeakerRole.clinician, "clinician-1", 8200, 10500, "Sorry to hear that. Any fever?"),
            (SpeakerRole.patient, "patient-1", 10700, 14500, "A little bit, I've felt warm on and off, maybe around a hundred point five at home."),
            (SpeakerRole.clinician, "clinician-1", 14700, 18000, "Any tooth pain, or pain when you lean forward?"),
            (SpeakerRole.patient, "patient-1", 18200, 22500, "Yeah, actually. Leaning forward makes the pressure worse, especially around my cheeks."),
            (SpeakerRole.clinician, "clinician-1", 22700, 25500, "How's your breathing? Any cough?"),
            (SpeakerRole.patient, "patient-1", 25700, 30000, "A bit of a cough, mostly at night, and some post-nasal drip."),
            (SpeakerRole.clinician, "clinician-1", 30200, 33000, "Any known allergies we should know about?"),
            (SpeakerRole.patient, "patient-1", 33200, 37500, "My seasonal allergies have been fine lately, the loratadine handles it."),
            (SpeakerRole.clinician, "clinician-1", 37700, 41000, "Good. Let me take a look at your sinuses and throat."),
            (SpeakerRole.clinician, "clinician-1", 41200, 47500, "There's tenderness over your maxillary sinuses and your throat looks a bit red, but your lungs sound clear."),
            (SpeakerRole.clinician, "clinician-1", 47700, 54000, "This looks like a sinus infection. Let's get you started on an antibiotic -- I'll prescribe amoxicillin 500 milligrams three times a day for ten days."),
            (SpeakerRole.patient, "patient-1", 54200, 56000, "Okay, whatever you think is best."),
            (SpeakerRole.clinician, "clinician-1", 56200, 64500, "In the meantime, a saline nasal rinse and an over-the-counter decongestant can help with the pressure. Come back if you're not improving in a week, or sooner if you spike a high fever."),
        ],
    )

    allergy_claim = Claim(
        encounter_id=encounter.id,
        text="documented penicillin allergy",
        claim_type=ClaimType.allergy,
        source_type=SourceType.ehr_data,
        source_reference="ehr-allergy-1",
        confidence=1.0,
        status=ClaimStatus.proposed,
    )
    congestion_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports facial pressure and thick nasal drainage for about a week",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[1].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    fever_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports low-grade fever, around 100.5 F at home",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[3].id),
        confidence=0.87,
        status=ClaimStatus.proposed,
    )
    positional_pressure_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports facial pressure worse when leaning forward, localized to the cheeks",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[5].id),
        confidence=0.86,
        status=ClaimStatus.proposed,
    )
    cough_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports nighttime cough with post-nasal drip",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[7].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    seasonal_allergy_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports seasonal allergies, well controlled with loratadine",
        claim_type=ClaimType.allergy,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[9].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    exam_claim = Claim(
        encounter_id=encounter.id,
        text="tenderness over maxillary sinuses, erythematous oropharynx, lungs clear",
        claim_type=ClaimType.exam_finding,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[11].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    assessment_claim = Claim(
        encounter_id=encounter.id,
        text="assessment: acute sinusitis",
        claim_type=ClaimType.assessment,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[12].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )
    prescription_claim = Claim(
        encounter_id=encounter.id,
        text="clinician prescribes amoxicillin 500mg three times daily for ten days",
        claim_type=ClaimType.medication,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[12].id),
        confidence=0.93,
        status=ClaimStatus.proposed,
    )
    rinse_claim = Claim(
        encounter_id=encounter.id,
        text="plan: saline nasal rinse and over-the-counter decongestant for symptomatic relief",
        claim_type=ClaimType.plan_item,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[14].id),
        confidence=0.87,
        status=ClaimStatus.proposed,
    )
    followup_claim = Claim(
        encounter_id=encounter.id,
        text="plan: follow up in one week if not improving, sooner if high fever develops",
        claim_type=ClaimType.plan_item,
        source_type=SourceType.clinician_observation,
        source_reference=str(segments[14].id),
        confidence=0.88,
        status=ClaimStatus.proposed,
    )

    all_claims = [
        allergy_claim,
        congestion_claim,
        fever_claim,
        positional_pressure_claim,
        cough_claim,
        seasonal_allergy_claim,
        exam_claim,
        assessment_claim,
        prescription_claim,
        rinse_claim,
        followup_claim,
    ]
    db.add_all(all_claims)
    db.flush()

    for claim in all_claims:
        if claim is prescription_claim:
            _add_verdicts(
                db,
                claim,
                safety=False,
                safety_rationale=(
                    "Amoxicillin is a penicillin-class antibiotic and this patient has a documented penicillin "
                    "allergy; cross-reactivity risk applies to related beta-lactams as well."
                ),
            )
        else:
            _add_verdicts(db, claim)
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
    """Scenario 3: a fatigue visit where the clinician actually asks several
    good follow-up questions -- sleep, appetite, mood, other symptoms -- and
    still can't pin down duration or severity, which is exactly what should
    trip the missing-context check. Left with its clarification question
    unresolved -- shows the Clarifications tab in action and the sign gate
    that blocks on it."""
    encounter = Encounter(patient_id=patient.id, clinician_id=clinician.id, status=EncounterStatus.in_progress)
    db.add(encounter)
    db.flush()

    segments = _add_segments(
        db,
        encounter,
        [
            (SpeakerRole.clinician, "clinician-1", 0, 2500, "Hi, come on in. What's been going on?"),
            (SpeakerRole.patient, "patient-1", 2700, 6000, "I've just been feeling really tired lately. Like, more than usual."),
            (SpeakerRole.clinician, "clinician-1", 6200, 8500, "How long has this been going on?"),
            (SpeakerRole.patient, "patient-1", 8700, 14000, "Honestly, it's hard to say. It kind of crept up on me. Maybe a few weeks? I'm not totally sure."),
            (SpeakerRole.clinician, "clinician-1", 14200, 18000, "Has anything changed recently -- new stress, sleep schedule, diet?"),
            (SpeakerRole.patient, "patient-1", 18200, 23000, "Not really, work's been about the same. Sleep is fine, I'm getting my usual seven or eight hours."),
            (SpeakerRole.clinician, "clinician-1", 23200, 26000, "Any changes in appetite or weight?"),
            (SpeakerRole.patient, "patient-1", 26200, 29000, "No, eating normally, weight's been stable."),
            (SpeakerRole.clinician, "clinician-1", 29200, 34000, "Any other symptoms -- shortness of breath, feeling cold all the time, low mood?"),
            (SpeakerRole.patient, "patient-1", 34200, 39000, "No, none of that. I just feel drained, even after a full night's sleep."),
        ],
    )

    fatigue_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports fatigue for an uncertain duration, possibly a few weeks",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[3].id),
        confidence=0.9,
        status=ClaimStatus.proposed,
    )
    sleep_claim = Claim(
        encounter_id=encounter.id,
        text="patient reports unchanged sleep schedule, seven to eight hours nightly",
        claim_type=ClaimType.history,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[5].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    appetite_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies changes in appetite or weight",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[7].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    other_symptoms_claim = Claim(
        encounter_id=encounter.id,
        text="patient denies shortness of breath, cold intolerance, or low mood",
        claim_type=ClaimType.symptom,
        source_type=SourceType.patient_speech,
        source_reference=str(segments[9].id),
        confidence=0.85,
        status=ClaimStatus.proposed,
    )
    db.add_all([fatigue_claim, sleep_claim, appetite_claim, other_symptoms_claim])
    db.flush()

    missing_context_rationale = (
        "Duration and severity of the fatigue remain unspecified even after follow-up questions -- "
        "the patient could not pin down a clear onset or rate how severe it feels."
    )
    _add_verdicts(db, fatigue_claim, missing_context=False, missing_context_rationale=missing_context_rationale)
    _add_verdicts(db, sleep_claim)
    _add_verdicts(db, appetite_claim)
    _add_verdicts(db, other_symptoms_claim)
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
