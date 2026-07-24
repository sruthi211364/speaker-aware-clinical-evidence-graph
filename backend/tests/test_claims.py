from unittest.mock import patch

from app.services.claude_service import ClaimExtractionResult, ExtractedClaim


def _seed_encounter(client):
    resp = client.post("/encounters", json={})
    assert resp.status_code == 201
    return resp.json()


def test_ehr_context_ingest_creates_claims_without_calling_claude(client):
    encounter = _seed_encounter(client)

    resp = client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "allergy", "text": "documented penicillin allergy", "record_id": "ehr-1"}]},
    )
    assert resp.status_code == 201
    claims = resp.json()
    assert len(claims) == 1
    assert claims[0]["source_type"] == "ehr_data"
    assert claims[0]["status"] == "proposed"


def test_extract_claims_maps_model_output_to_claim_rows(client):
    encounter = _seed_encounter(client)

    transcript_resp = client.post(
        f"/encounters/{encounter['id']}/transcript",
        json={
            "segments": [
                {"speaker_role": "clinician", "start_ms": 0, "end_ms": 1000, "text": "What brings you in?"},
                {"speaker_role": "patient", "start_ms": 1000, "end_ms": 5000, "text": "I've had a headache for two days."},
            ]
        },
    )
    assert transcript_resp.status_code == 201

    fake_result = ClaimExtractionResult(
        claims=[
            ExtractedClaim(
                text="patient reports headache for two days",
                claim_type="symptom",
                source_segment_index=1,
                confidence=0.92,
            )
        ]
    )

    with patch("app.api.claims.extract_claims_from_transcript", return_value=fake_result):
        resp = client.post(f"/encounters/{encounter['id']}/claims/extract")

    assert resp.status_code == 201
    claims = resp.json()
    assert len(claims) == 1
    assert claims[0]["text"] == "patient reports headache for two days"
    assert claims[0]["claim_type"] == "symptom"
    assert claims[0]["source_type"] == "patient_speech"
    assert claims[0]["status"] == "proposed"

    # Re-running extraction is idempotent -- no duplicate claims.
    with patch("app.api.claims.extract_claims_from_transcript", return_value=fake_result) as mock_extract:
        resp2 = client.post(f"/encounters/{encounter['id']}/claims/extract")
    assert resp2.status_code == 201
    assert len(resp2.json()) == 1
    mock_extract.assert_not_called()


def test_extract_claims_drops_claims_citing_unknown_segment_index(client):
    encounter = _seed_encounter(client)

    client.post(
        f"/encounters/{encounter['id']}/transcript",
        json={"segments": [{"speaker_role": "patient", "start_ms": 0, "end_ms": 1000, "text": "My chest hurts."}]},
    )

    fake_result = ClaimExtractionResult(
        claims=[
            ExtractedClaim(
                text="a hallucinated claim citing a segment that doesn't exist",
                claim_type="symptom",
                source_segment_index=99,
                confidence=0.5,
            )
        ]
    )

    with patch("app.api.claims.extract_claims_from_transcript", return_value=fake_result):
        resp = client.post(f"/encounters/{encounter['id']}/claims/extract")

    assert resp.status_code == 201
    assert resp.json() == []
