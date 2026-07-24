from unittest.mock import patch

from app.models import VocabularyTerm


def _fake_term(code_system="SNOMED", code="29857009", display="Chest pain"):
    return VocabularyTerm(code_system=code_system, code=code, display=display, embedding=[0.0] * 384)


def _seed_encounter_with_claims(client):
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
    return encounter


def test_normalize_terminology_codes_claim_with_matching_vocabulary(client):
    encounter = _seed_encounter_with_claims(client)

    with patch("app.pipeline.steps.retrieve_vocabulary_term", return_value=(_fake_term(), 0.9)):
        resp = client.post(f"/encounters/{encounter['id']}/claims/normalize")

    assert resp.status_code == 201
    normalized = resp.json()
    # Only the symptom claim maps to a vocabulary (SNOMED); plan_item has none.
    assert len(normalized) == 1
    assert normalized[0]["normalized_code_system"] == "SNOMED"
    assert normalized[0]["normalized_code"] == "29857009"
    assert normalized[0]["normalized_display"] == "Chest pain"


def test_normalize_terminology_skips_claim_types_without_a_vocabulary(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "other", "text": "miscellaneous note", "record_id": "a"}]},
    )

    with patch("app.pipeline.steps.retrieve_vocabulary_term") as mock_retrieve:
        resp = client.post(f"/encounters/{encounter['id']}/claims/normalize")

    assert resp.status_code == 201
    assert resp.json() == []
    mock_retrieve.assert_not_called()


def test_normalize_terminology_skips_unsupported_claims(client):
    encounter = client.post("/encounters", json={}).json()
    # No record_id -> no source_reference -> will fail the support check.
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "patient reports fatigue"}]},
    )
    with patch("app.services.policy_engine.run_policy_checks") as mock_checks:
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
    mock_checks.assert_not_called()  # confirms the claim is unsupported before we proceed

    with patch("app.pipeline.steps.retrieve_vocabulary_term") as mock_retrieve:
        resp = client.post(f"/encounters/{encounter['id']}/claims/normalize")

    assert resp.status_code == 201
    assert resp.json() == []
    mock_retrieve.assert_not_called()


def test_normalize_terminology_is_idempotent_per_claim(client):
    encounter = _seed_encounter_with_claims(client)

    with patch(
        "app.pipeline.steps.retrieve_vocabulary_term", return_value=(_fake_term(), 0.9)
    ) as mock_retrieve:
        client.post(f"/encounters/{encounter['id']}/claims/normalize")
        resp2 = client.post(f"/encounters/{encounter['id']}/claims/normalize")

    assert resp2.status_code == 201
    assert resp2.json() == []  # nothing left to normalize
    mock_retrieve.assert_called_once()
