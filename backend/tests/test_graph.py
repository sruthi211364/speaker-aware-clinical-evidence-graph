from unittest.mock import patch

from app.services.claude_service import ClaudeRequestError, EdgeExtractionResult, ExtractedEdge


def _seed_encounter_with_two_claims(client):
    encounter = client.post("/encounters", json={}).json()

    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={
            "items": [
                {"claim_type": "symptom", "text": "patient reports chest pain since three days ago", "record_id": "a"},
                {"claim_type": "symptom", "text": "caregiver reports chest pain since last week", "record_id": "b"},
            ]
        },
    )
    return encounter


def test_build_claim_graph_maps_edges_to_claim_ids(client):
    encounter = _seed_encounter_with_two_claims(client)
    claims = client.get(f"/encounters/{encounter['id']}/claims").json()
    assert len(claims) == 2

    fake_result = EdgeExtractionResult(
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

    with patch("app.pipeline.steps.generate_claim_edges", return_value=fake_result):
        resp = client.post(f"/encounters/{encounter['id']}/claim-graph/build")

    assert resp.status_code == 201
    edges = resp.json()
    assert len(edges) == 1
    assert edges[0]["relation"] == "contradicts"
    assert {edges[0]["source_claim_id"], edges[0]["target_claim_id"]} == {c["id"] for c in claims}

    # Idempotent: rebuilding does not duplicate or re-call Claude.
    with patch("app.pipeline.steps.generate_claim_edges", return_value=fake_result) as mock_gen:
        resp2 = client.post(f"/encounters/{encounter['id']}/claim-graph/build")
    assert resp2.status_code == 201
    assert len(resp2.json()) == 1
    mock_gen.assert_not_called()


def test_get_claim_graph_returns_claims_and_edges(client):
    encounter = _seed_encounter_with_two_claims(client)

    fake_result = EdgeExtractionResult(
        edges=[
            ExtractedEdge(
                source_claim_index=0,
                target_claim_index=1,
                relation="contradicts",
                rationale="Different onset timelines.",
                confidence=0.9,
            )
        ]
    )
    with patch("app.pipeline.steps.generate_claim_edges", return_value=fake_result):
        client.post(f"/encounters/{encounter['id']}/claim-graph/build")

    resp = client.get(f"/encounters/{encounter['id']}/claim-graph")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["claims"]) == 2
    assert len(body["edges"]) == 1


def test_build_claim_graph_drops_edges_citing_unknown_index(client):
    encounter = _seed_encounter_with_two_claims(client)

    fake_result = EdgeExtractionResult(
        edges=[
            ExtractedEdge(
                source_claim_index=0,
                target_claim_index=99,
                relation="contradicts",
                rationale="Hallucinated edge to a claim index that doesn't exist.",
                confidence=0.5,
            )
        ]
    )
    with patch("app.pipeline.steps.generate_claim_edges", return_value=fake_result):
        resp = client.post(f"/encounters/{encounter['id']}/claim-graph/build")

    assert resp.status_code == 201
    assert resp.json() == []


def test_build_claim_graph_with_fewer_than_two_claims_skips_claude(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "allergy", "text": "penicillin allergy"}]},
    )

    with patch("app.pipeline.steps.generate_claim_edges") as mock_gen:
        resp = client.post(f"/encounters/{encounter['id']}/claim-graph/build")

    assert resp.status_code == 201
    assert resp.json() == []
    mock_gen.assert_not_called()


def test_build_claim_graph_surfaces_a_failed_claude_request_as_502(client):
    encounter = _seed_encounter_with_two_claims(client)

    with patch(
        "app.pipeline.steps.generate_claim_edges",
        side_effect=ClaudeRequestError("Edge generation request to Claude failed: rate limited"),
    ):
        resp = client.post(f"/encounters/{encounter['id']}/claim-graph/build")

    assert resp.status_code == 502
    assert "rate limited" in resp.json()["detail"]
