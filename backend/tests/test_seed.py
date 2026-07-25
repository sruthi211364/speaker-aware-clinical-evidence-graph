from unittest.mock import patch

from app.models import User
from app.seed import seed_contradiction_encounter, seed_missing_context_encounter, seed_safety_flag_encounter

# seed_*_encounter call ground_claims_step and normalize_terminology_step,
# which use pgvector's cosine_distance() -- not available on the SQLite test
# DB. Both retrieval calls are mocked to no-ops here so the rest of each
# seed function's logic (claims, edges, verdicts, note compilation) can be
# exercised directly; live behavior against real Postgres + pgvector is
# verified separately (see README).


def _make_users(db_session) -> tuple[User, User]:
    clinician = User(display_name="Dr. Test", role="clinician", email="test.clinician@example.com")
    patient = User(display_name="Test Patient", role="patient", email="test.patient@example.com")
    db_session.add_all([clinician, patient])
    db_session.flush()
    return clinician, patient


def test_seed_contradiction_encounter_produces_conflict_line(db_session):
    clinician, patient = _make_users(db_session)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[]),
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[]),
        patch("app.pipeline.steps.retrieve_vocabulary_term", return_value=None),
    ):
        encounter = seed_contradiction_encounter(db_session, clinician, patient)

    from app.models import Claim, ClaimEdge, SoapNote

    claims = db_session.query(Claim).filter_by(encounter_id=encounter.id).all()
    assert len(claims) == 17
    statuses = {c.status.value for c in claims}
    assert statuses == {"contradicted", "supported"}
    assert sum(1 for c in claims if c.status.value == "contradicted") == 2

    edges = db_session.query(ClaimEdge).all()
    assert len(edges) == 1
    assert edges[0].relation.value == "contradicts"

    note = db_session.query(SoapNote).filter_by(encounter_id=encounter.id).first()
    assert note is not None
    assert note.status.value == "under_review"
    conflict_lines = [line for line in note.lines if line.is_conflict]
    assert len(conflict_lines) == 1
    assert len(conflict_lines[0].claim_links) == 2
    # A real encounter touches all four SOAP sections, not just Subjective.
    sections = {line.section.value for line in note.lines}
    assert sections == {"subjective", "objective", "assessment", "plan"}


def test_seed_safety_flag_encounter_signs_and_exports(db_session):
    clinician, patient = _make_users(db_session)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[]),
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[]),
        patch("app.pipeline.steps.retrieve_vocabulary_term", return_value=None),
    ):
        encounter = seed_safety_flag_encounter(db_session, clinician, patient)

    from app.models import Claim, MockEhrSubmission, SoapNote

    claims = db_session.query(Claim).filter_by(encounter_id=encounter.id).all()
    assert len(claims) == 11
    unsafe = [c for c in claims if c.status.value == "unsafe"]
    assert len(unsafe) == 1
    assert "amoxicillin" in unsafe[0].text

    note = db_session.query(SoapNote).filter_by(encounter_id=encounter.id).first()
    assert note.status.value == "signed"
    assert note.signed_by == clinician.id
    sections = {line.section.value for line in note.lines}
    assert sections == {"subjective", "objective", "assessment", "plan"}

    submissions = db_session.query(MockEhrSubmission).filter_by(encounter_id=encounter.id).all()
    assert len(submissions) == 1
    resource_types = [e["resource"]["resourceType"] for e in submissions[0].bundle["entry"]]
    assert "Composition" in resource_types
    assert "DocumentReference" in resource_types


def test_seed_missing_context_encounter_leaves_clarification_unresolved(db_session):
    clinician, patient = _make_users(db_session)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[]),
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[]),
        patch("app.pipeline.steps.retrieve_vocabulary_term", return_value=None),
    ):
        encounter = seed_missing_context_encounter(db_session, clinician, patient)

    from app.models import ClarificationQuestion, Claim

    claims = db_session.query(Claim).filter_by(encounter_id=encounter.id).all()
    assert len(claims) == 4
    missing_context_claims = [c for c in claims if c.status.value == "missing_context"]
    assert len(missing_context_claims) == 1
    fatigue_claim = missing_context_claims[0]
    assert "fatigue" in fatigue_claim.text
    assert {c.status.value for c in claims if c is not fatigue_claim} == {"supported"}

    clarification = db_session.query(ClarificationQuestion).filter_by(encounter_id=encounter.id).first()
    assert clarification is not None
    assert clarification.resolved is False
    assert clarification.triggering_claim_id == fatigue_claim.id
