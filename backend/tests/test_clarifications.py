from unittest.mock import patch

from app.services.claude_service import PolicyCheckResult


def _seed_clarification(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "patient reports chest pain", "record_id": "a"}]},
    )
    result = PolicyCheckResult(
        contradicts_history=False,
        temporally_ambiguous=False,
        missing_context=True,
        missing_context_rationale="Severity and radiation are not documented.",
        clarification_question="Can you describe the severity and whether the pain radiates anywhere?",
        clinical_safety_flag=False,
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=result):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")

    clarification = client.get(f"/encounters/{encounter['id']}/clarifications").json()[0]
    return encounter, clarification


def test_answer_clarification_creates_clinician_judgment_claim(client):
    encounter, clarification = _seed_clarification(client)

    resp = client.post(
        f"/encounters/{encounter['id']}/clarifications/{clarification['id']}/answer",
        json={"answer_text": "Severity is 6/10, radiates to the left arm."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["resolved"] is True
    assert body["resolved_by_claim_id"] is not None

    claims = client.get(f"/encounters/{encounter['id']}/claims").json()
    answer_claim = next(c for c in claims if c["id"] == body["resolved_by_claim_id"])
    assert answer_claim["source_type"] == "clinician_judgment"
    assert answer_claim["text"] == "Severity is 6/10, radiates to the left arm."


def test_answer_already_resolved_clarification_returns_409(client):
    encounter, clarification = _seed_clarification(client)

    client.post(
        f"/encounters/{encounter['id']}/clarifications/{clarification['id']}/answer",
        json={"answer_text": "First answer."},
    )
    resp2 = client.post(
        f"/encounters/{encounter['id']}/clarifications/{clarification['id']}/answer",
        json={"answer_text": "Second answer."},
    )
    assert resp2.status_code == 409


def test_answer_clarification_not_on_encounter_returns_404(client):
    encounter_a, clarification = _seed_clarification(client)
    encounter_b = client.post("/encounters", json={}).json()

    resp = client.post(
        f"/encounters/{encounter_b['id']}/clarifications/{clarification['id']}/answer",
        json={"answer_text": "Answer."},
    )
    assert resp.status_code == 404
