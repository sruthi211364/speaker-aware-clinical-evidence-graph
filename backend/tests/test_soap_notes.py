from unittest.mock import patch

from app.models import Claim, SoapNote
from app.models.enums import ClaimStatus, ClaimType, NoteStatus, SourceType
from app.services.claude_service import (
    ClaimExtractionResult,
    EdgeExtractionResult,
    ExtractedClaim,
    ExtractedEdge,
    PolicyCheckResult,
)


def _clean_check_result(**overrides) -> PolicyCheckResult:
    defaults = dict(
        contradicts_history=False,
        contradicts_history_rationale=None,
        temporally_ambiguous=False,
        temporal_ambiguity_rationale=None,
        missing_context=False,
        missing_context_rationale=None,
        clarification_question=None,
        clinical_safety_flag=False,
        clinical_safety_rationale=None,
    )
    defaults.update(overrides)
    return PolicyCheckResult(**defaults)


def _seed_supported_claims(client):
    """One symptom claim (-> subjective) and one plan_item claim (-> plan),
    both pushed through policy-check clean so they land as 'supported'."""
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={
            "items": [
                {"claim_type": "symptom", "text": "patient reports chest pain", "record_id": "a"},
                {"claim_type": "plan_item", "text": "follow up in two weeks", "record_id": "b"},
            ]
        },
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=_clean_check_result()):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
    return encounter


def _seed_contradicted_pair(client):
    """Patient and caregiver claims (via transcript extraction, so they carry
    real patient_speech/caregiver_report source types) that a mocked edge
    extraction marks as contradicting."""
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/transcript",
        json={
            "segments": [
                {"speaker_role": "patient", "start_ms": 0, "end_ms": 1000, "text": "My chest has hurt for three days."},
                {"speaker_role": "caregiver", "start_ms": 1000, "end_ms": 2000, "text": "It's been going on a week."},
            ]
        },
    )
    fake_claims = ClaimExtractionResult(
        claims=[
            ExtractedClaim(
                text="patient reports chest pain since three days ago",
                claim_type="symptom",
                source_segment_index=0,
                confidence=0.9,
            ),
            ExtractedClaim(
                text="caregiver reports chest pain since last week",
                claim_type="symptom",
                source_segment_index=1,
                confidence=0.9,
            ),
        ]
    )
    with patch("app.pipeline.steps.extract_claims_from_transcript", return_value=fake_claims):
        client.post(f"/encounters/{encounter['id']}/claims/extract")

    fake_edges = EdgeExtractionResult(
        edges=[
            ExtractedEdge(
                source_claim_index=0,
                target_claim_index=1,
                relation="contradicts",
                rationale="Different onset timelines from patient vs. caregiver.",
                confidence=0.9,
            )
        ]
    )
    with patch("app.pipeline.steps.generate_claim_edges", return_value=fake_edges):
        client.post(f"/encounters/{encounter['id']}/claim-graph/build")
    with patch("app.services.policy_engine.run_policy_checks", return_value=_clean_check_result()):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
    return encounter


def test_compile_note_groups_supported_claims_into_sections(client):
    encounter = _seed_supported_claims(client)

    resp = client.post(f"/encounters/{encounter['id']}/notes/compile")
    assert resp.status_code == 201
    note = resp.json()
    assert note["status"] == "draft"
    assert note["version"] == 1

    sections = {line["section"] for line in note["lines"]}
    assert sections == {"subjective", "plan"}
    subjective_line = next(l for l in note["lines"] if l["section"] == "subjective")
    assert "chest pain" in subjective_line["text"]
    assert len(subjective_line["claim_ids"]) == 1
    assert subjective_line["is_conflict"] is False


def test_compile_note_is_idempotent_per_encounter(client):
    encounter = _seed_supported_claims(client)

    resp1 = client.post(f"/encounters/{encounter['id']}/notes/compile")
    resp2 = client.post(f"/encounters/{encounter['id']}/notes/compile")

    assert resp1.json()["id"] == resp2.json()["id"]
    assert resp2.json()["version"] == 1


def test_compile_note_excludes_claims_never_run_through_policy_check(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "unvetted claim", "record_id": "a"}]},
    )
    # Never called /claims/policy-check -- claim stays "proposed".

    resp = client.post(f"/encounters/{encounter['id']}/notes/compile")
    assert resp.status_code == 201
    assert resp.json()["lines"] == []


def test_compile_note_excludes_unsupported_claims(client):
    encounter = client.post("/encounters", json={}).json()
    # No record_id -> no source_reference -> fails the support check -> "unsupported".
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "claim with no source"}]},
    )
    with patch("app.services.policy_engine.run_policy_checks") as mock_checks:
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
    mock_checks.assert_not_called()  # short-circuits before the Claude call

    resp = client.post(f"/encounters/{encounter['id']}/notes/compile")
    assert resp.status_code == 201
    assert resp.json()["lines"] == []


def test_compile_note_merges_contradicted_pair_into_one_conflict_line(client):
    encounter = _seed_contradicted_pair(client)
    claims = client.get(f"/encounters/{encounter['id']}/claims").json()
    assert {c["status"] for c in claims} == {"contradicted"}

    resp = client.post(f"/encounters/{encounter['id']}/notes/compile")
    assert resp.status_code == 201
    lines = resp.json()["lines"]
    assert len(lines) == 1
    conflict_line = lines[0]
    assert conflict_line["is_conflict"] is True
    assert conflict_line["section"] == "subjective"
    assert set(conflict_line["claim_ids"]) == {c["id"] for c in claims}
    assert "Patient:" in conflict_line["text"]
    assert "Caregiver:" in conflict_line["text"]


def test_get_latest_note_404_before_compiling(client):
    encounter = client.post("/encounters", json={}).json()
    resp = client.get(f"/encounters/{encounter['id']}/notes/latest")
    assert resp.status_code == 404


def test_accept_edit_reject_line_write_attestations(client):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    lines = note["lines"]
    accept_line = lines[0]
    edit_line = lines[1]

    accept_resp = client.post(
        f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{accept_line['id']}/accept"
    )
    assert accept_resp.status_code == 201
    assert accept_resp.json()["action"] == "accepted"
    assert accept_resp.json()["claim_id"] == accept_line["claim_ids"][0]

    edit_resp = client.post(
        f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{edit_line['id']}/edit",
        json={"text": "Plan: follow up in one week instead"},
    )
    assert edit_resp.status_code == 201
    assert edit_resp.json()["action"] == "edited"
    assert edit_resp.json()["before_value"] != edit_resp.json()["after_value"]

    reject_resp = client.post(
        f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{accept_line['id']}/reject"
    )
    assert reject_resp.status_code == 201
    assert reject_resp.json()["action"] == "rejected"
    assert reject_resp.json()["after_value"] is None

    refreshed = client.get(f"/encounters/{encounter['id']}/notes/latest").json()
    edited = next(l for l in refreshed["lines"] if l["id"] == edit_line["id"])
    assert edited["text"] == "Plan: follow up in one week instead"
    rejected = next(l for l in refreshed["lines"] if l["id"] == accept_line["id"])
    assert rejected["is_rejected"] is True
    # Rejected lines stay in the note rather than disappearing.
    assert len(refreshed["lines"]) == 2

    attestations = client.get(f"/encounters/{encounter['id']}/attestations").json()
    assert [a["action"] for a in attestations] == ["accepted", "edited", "rejected"]


def test_edit_and_reject_are_blocked_on_a_signed_note(client, db_session):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    line = note["lines"][0]

    db_note = db_session.get(SoapNote, note["id"])
    db_note.status = NoteStatus.signed
    db_session.commit()

    edit_resp = client.post(
        f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{line['id']}/edit",
        json={"text": "should not apply"},
    )
    assert edit_resp.status_code == 409

    reject_resp = client.post(
        f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{line['id']}/reject"
    )
    assert reject_resp.status_code == 409


def test_reject_single_claim_line_marks_underlying_claim_rejected(client):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    line = note["lines"][0]
    assert len(line["claim_ids"]) == 1

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{line['id']}/reject")
    assert resp.status_code == 201

    claim = next(c for c in client.get(f"/encounters/{encounter['id']}/claims").json() if c["id"] == line["claim_ids"][0])
    assert claim["status"] == "rejected"


def test_reject_conflict_line_does_not_change_either_claims_status(client):
    encounter = _seed_contradicted_pair(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    conflict_line = note["lines"][0]
    assert len(conflict_line["claim_ids"]) == 2

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/lines/{conflict_line['id']}/reject")
    assert resp.status_code == 201

    claims = client.get(f"/encounters/{encounter['id']}/claims").json()
    assert {c["status"] for c in claims} == {"contradicted"}


def test_note_and_line_lookup_404_on_mismatched_encounter(client):
    encounter1 = _seed_supported_claims(client)
    encounter2 = client.post("/encounters", json={}).json()
    note1 = client.post(f"/encounters/{encounter1['id']}/notes/compile").json()

    resp = client.post(f"/encounters/{encounter2['id']}/notes/{note1['id']}/lines/{note1['lines'][0]['id']}/accept")
    assert resp.status_code == 404


def test_sign_note_locks_it_and_advances_encounter_status(client):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")
    assert resp.status_code == 201
    signed = resp.json()
    assert signed["status"] == "signed"
    assert signed["signed_by"] is not None
    assert signed["signed_at"] is not None

    encounter_after = client.get(f"/encounters/{encounter['id']}").json()
    assert encounter_after["status"] == "signed"

    attestations = client.get(f"/encounters/{encounter['id']}/attestations").json()
    assert attestations[-1]["action"] == "signed"
    assert attestations[-1]["note_line_id"] is None


def test_sign_note_is_blocked_while_a_clarification_is_unresolved(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "patient reports fatigue", "record_id": "c"}]},
    )
    missing_context_result = _clean_check_result(
        missing_context=True,
        missing_context_rationale="Duration and severity are not documented.",
        clarification_question="How long has the fatigue lasted, and how severe is it?",
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=missing_context_result):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")
    assert resp.status_code == 409
    assert "unresolved" in resp.json()["detail"]


def test_sign_note_rejects_already_signed(client):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")
    assert resp.status_code == 409


def test_amend_requires_latest_version_to_be_signed(client):
    encounter = _seed_supported_claims(client)
    client.post(f"/encounters/{encounter['id']}/notes/compile").json()

    resp = client.post(f"/encounters/{encounter['id']}/notes/amend")
    assert resp.status_code == 409


def test_amend_after_signing_creates_new_version_reflecting_current_claims(client, db_session):
    encounter = _seed_supported_claims(client)
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")

    # Simulates a claim that reached "supported" after signing (e.g. via a
    # clarification answered later and independently policy-checked) --
    # added directly since /claims/policy-check's idempotency is per
    # encounter, not per claim, and isn't what's under test here.
    db_session.add(
        Claim(
            encounter_id=encounter["id"],
            text="blood pressure 130/85",
            claim_type=ClaimType.vital,
            source_type=SourceType.ehr_data,
            source_reference="d",
            confidence=1.0,
            status=ClaimStatus.supported,
        )
    )
    db_session.commit()

    resp = client.post(f"/encounters/{encounter['id']}/notes/amend")
    assert resp.status_code == 201
    amended = resp.json()
    assert amended["version"] == 2
    assert amended["status"] == "draft"
    assert any("blood pressure" in line["text"] for line in amended["lines"])

    encounter_after = client.get(f"/encounters/{encounter['id']}").json()
    assert encounter_after["status"] == "drafted"

    notes = client.get(f"/encounters/{encounter['id']}/notes").json()
    assert [n["version"] for n in notes] == [1, 2]
    assert notes[0]["status"] == "signed"
