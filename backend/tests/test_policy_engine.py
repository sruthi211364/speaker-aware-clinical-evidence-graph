from unittest.mock import patch

from app.services.claude_service import PolicyCheckResult


def _seed_encounter_with_claim(client, text="patient reports chest pain", claim_type="symptom", record_id="a"):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": claim_type, "text": text, "record_id": record_id}]},
    )
    return encounter


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


def test_policy_check_passes_clean_claim_as_supported(client):
    encounter = _seed_encounter_with_claim(client)

    with patch("app.services.policy_engine.run_policy_checks", return_value=_clean_check_result()):
        resp = client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    assert resp.status_code == 201
    verdicts = resp.json()
    assert len(verdicts) == 5
    assert all(v["passed"] for v in verdicts)

    claim = client.get(f"/encounters/{encounter['id']}/claims").json()[0]
    assert claim["status"] == "supported"


def test_policy_check_flags_claim_with_no_source_reference_as_unsupported(client):
    encounter = _seed_encounter_with_claim(client, record_id=None)

    with patch("app.services.policy_engine.run_policy_checks") as mock_checks:
        resp = client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    assert resp.status_code == 201
    verdicts = resp.json()
    assert len(verdicts) == 1
    assert verdicts[0]["check_type"] == "support"
    assert verdicts[0]["passed"] is False
    mock_checks.assert_not_called()  # unsupported claims skip the remaining checks

    claim = client.get(f"/encounters/{encounter['id']}/claims").json()[0]
    assert claim["status"] == "unsupported"


def test_policy_check_clinical_safety_flag_creates_unsafe_status(client):
    encounter = _seed_encounter_with_claim(
        client, text="clinician prescribes amoxicillin despite documented penicillin allergy", claim_type="allergy"
    )

    result = _clean_check_result(
        clinical_safety_flag=True,
        clinical_safety_rationale="Amoxicillin conflicts with documented penicillin allergy.",
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=result):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    claim = client.get(f"/encounters/{encounter['id']}/claims").json()[0]
    assert claim["status"] == "unsafe"

    verdicts = client.get(f"/encounters/{encounter['id']}/policy-verdicts").json()
    safety_verdict = next(v for v in verdicts if v["check_type"] == "clinical_safety")
    assert safety_verdict["passed"] is False
    assert "penicillin" in safety_verdict["rationale"]


def test_policy_check_missing_context_creates_clarification_question(client):
    encounter = _seed_encounter_with_claim(client, text="patient reports chest pain")

    result = _clean_check_result(
        missing_context=True,
        missing_context_rationale="Severity and radiation are not documented.",
        clarification_question="Can you describe the severity and whether the pain radiates anywhere?",
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=result):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    claim = client.get(f"/encounters/{encounter['id']}/claims").json()[0]
    assert claim["status"] == "missing_context"

    clarifications = client.get(f"/encounters/{encounter['id']}/clarifications").json()
    assert len(clarifications) == 1
    assert clarifications[0]["triggering_claim_id"] == claim["id"]
    assert clarifications[0]["resolved"] is False
    assert "radiat" in clarifications[0]["question_text"]


def test_policy_check_is_idempotent(client):
    encounter = _seed_encounter_with_claim(client)

    with patch("app.services.policy_engine.run_policy_checks", return_value=_clean_check_result()) as mock_checks:
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
        resp2 = client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    assert resp2.status_code == 201
    assert len(resp2.json()) == 5
    mock_checks.assert_called_once()
