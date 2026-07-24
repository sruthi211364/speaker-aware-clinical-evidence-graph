from unittest.mock import patch

from app.services.claude_service import ClaudeNotConfiguredError

# The LangGraph pipeline runner uses its own DB sessions (SessionLocal) and a
# real-Postgres-only checkpointer (see app/pipeline/checkpointer.py), so it
# can't run against the SQLite test DB. These tests mock the pipeline entry
# points and check the endpoint's HTTP contract; the actual LangGraph
# mechanics are verified live against the real Postgres stack (see README).


def test_run_pipeline_returns_result_summary(client):
    encounter = client.post("/encounters", json={}).json()

    fake_result = {
        "transcript_segment_count": 3,
        "claim_count": 2,
        "edge_count": 1,
        "citation_count": 4,
        "verdict_count": 10,
        "open_clarification_count": 1,
        "normalized_claim_count": 2,
    }
    with patch("app.api.pipeline.run_pipeline", return_value=fake_result) as mock_run:
        resp = client.post(f"/encounters/{encounter['id']}/pipeline/run")

    assert resp.status_code == 201
    body = resp.json()
    assert body["encounter_id"] == encounter["id"]
    assert body["claim_count"] == 2
    assert body["open_clarification_count"] == 1
    mock_run.assert_called_once_with(encounter["id"])


def test_run_pipeline_surfaces_missing_api_key_as_503(client):
    encounter = client.post("/encounters", json={}).json()

    with patch("app.api.pipeline.run_pipeline", side_effect=ClaudeNotConfiguredError("no key")):
        resp = client.post(f"/encounters/{encounter['id']}/pipeline/run")

    assert resp.status_code == 503


def test_get_pipeline_trace_returns_node_history(client):
    encounter = client.post("/encounters", json={}).json()

    fake_trace = [
        {"node": None, "step": -1, "next": ["ingest"], "values": {}},
        {"node": "ingest", "step": 0, "next": ["extract_claims"], "values": {"transcript_segment_count": 3}},
    ]
    with patch("app.api.pipeline.get_pipeline_trace", return_value=fake_trace):
        resp = client.get(f"/encounters/{encounter['id']}/pipeline/trace")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[1]["node"] == "ingest"


def test_pipeline_endpoints_404_for_unknown_encounter(client):
    resp = client.post("/encounters/00000000-0000-0000-0000-000000000000/pipeline/run")
    assert resp.status_code == 404
