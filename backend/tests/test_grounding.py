from unittest.mock import patch

from app.models import ClinicalKnowledgeChunk, PatientHistoryChunk


def _fake_knowledge_chunk(text="Chest pain documentation requires severity, radiation, and associated symptoms."):
    return ClinicalKnowledgeChunk(
        source_identifier="chest_pain_documentation_standard",
        title="Chest pain documentation requirements",
        content=text,
        embedding=[0.0] * 384,
    )


def _fake_history_chunk(text="Prior visit: brief chest tightness unrelated to exertion."):
    return PatientHistoryChunk(
        patient_id="00000000-0000-0000-0000-000000000000",
        source_encounter_label="prior visit",
        content=text,
        embedding=[0.0] * 384,
    )


def _seed_encounter_with_claim(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "patient reports chest pain", "record_id": "a"}]},
    )
    return encounter


def test_ground_claims_creates_citations_from_both_indexes(client):
    encounter = _seed_encounter_with_claim(client)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[(_fake_knowledge_chunk(), 0.8)]),
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[(_fake_history_chunk(), 0.7)]),
    ):
        resp = client.post(f"/encounters/{encounter['id']}/claims/ground")

    assert resp.status_code == 201
    citations = resp.json()
    assert len(citations) == 2
    source_types = {c["source_type"] for c in citations}
    assert source_types == {"guideline", "prior_encounter"}


def test_ground_claims_is_idempotent(client):
    encounter = _seed_encounter_with_claim(client)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[(_fake_knowledge_chunk(), 0.8)]) as mock_ck,
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[(_fake_history_chunk(), 0.7)]) as mock_ph,
    ):
        client.post(f"/encounters/{encounter['id']}/claims/ground")
        resp2 = client.post(f"/encounters/{encounter['id']}/claims/ground")

    assert resp2.status_code == 201
    assert len(resp2.json()) == 2
    mock_ck.assert_called_once()
    mock_ph.assert_called_once()


def test_get_claim_citations_returns_stored_citations(client):
    encounter = _seed_encounter_with_claim(client)

    with (
        patch("app.pipeline.steps.retrieve_clinical_knowledge", return_value=[(_fake_knowledge_chunk(), 0.8)]),
        patch("app.pipeline.steps.retrieve_patient_history", return_value=[]),
    ):
        citations = client.post(f"/encounters/{encounter['id']}/claims/ground").json()

    claim_id = citations[0]["claim_id"]
    resp = client.get(f"/encounters/{encounter['id']}/claims/{claim_id}/citations")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["source_type"] == "guideline"


def test_get_citations_for_claim_not_on_encounter_returns_404(client):
    encounter_a = _seed_encounter_with_claim(client)
    encounter_b = client.post("/encounters", json={}).json()

    claim_a = client.get(f"/encounters/{encounter_a['id']}/claims").json()[0]
    resp = client.get(f"/encounters/{encounter_b['id']}/claims/{claim_a['id']}/citations")
    assert resp.status_code == 404
