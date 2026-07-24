from unittest.mock import patch

from app.services.claude_service import PolicyCheckResult


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


def _seed_signed_note(client):
    """One symptom claim (normalized to a SNOMED code) and one plan_item
    claim (left uncoded), both supported, compiled and signed."""
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

    from app.models import VocabularyTerm

    def _fake_term():
        return VocabularyTerm(code_system="SNOMED", code="29857009", display="Chest pain", embedding=[0.0] * 384)

    with patch("app.pipeline.steps.retrieve_vocabulary_term", return_value=(_fake_term(), 0.9)):
        client.post(f"/encounters/{encounter['id']}/claims/normalize")

    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()
    client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/sign")
    return encounter, note


def test_export_fhir_requires_a_signed_note(client):
    encounter = client.post("/encounters", json={}).json()
    client.post(
        f"/encounters/{encounter['id']}/ehr-context",
        json={"items": [{"claim_type": "symptom", "text": "patient reports chest pain", "record_id": "a"}]},
    )
    with patch("app.services.policy_engine.run_policy_checks", return_value=_clean_check_result()):
        client.post(f"/encounters/{encounter['id']}/claims/policy-check")
    note = client.post(f"/encounters/{encounter['id']}/notes/compile").json()

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/export-fhir")
    assert resp.status_code == 409


def test_export_fhir_builds_a_valid_bundle_with_coded_and_uncoded_lines(client):
    encounter, note = _seed_signed_note(client)

    resp = client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/export-fhir")
    assert resp.status_code == 201
    submission = resp.json()
    assert submission["encounter_id"] == encounter["id"]
    assert submission["note_id"] == note["id"]

    bundle = submission["bundle"]
    assert bundle["resourceType"] == "Bundle"
    resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert resource_types.count("DocumentReference") == 1
    assert resource_types.count("Composition") == 1
    assert resource_types.count("Observation") == 2  # symptom (subjective) + plan_item (plan)
    assert resource_types.count("Condition") == 0  # no assessment-type claims in this seed

    observations = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    coded = next(o for o in observations if "coding" in o.get("code", {}))
    assert coded["code"]["coding"][0]["system"] == "http://snomed.info/sct"
    assert coded["code"]["coding"][0]["code"] == "29857009"
    uncoded = next(o for o in observations if "coding" not in o.get("code", {}))
    assert uncoded["code"]["text"] == "follow up in two weeks"

    composition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Composition")
    assert composition["status"] == "final"
    section_titles = {s["title"] for s in composition["section"]}
    assert section_titles == {"Subjective", "Plan"}

    docref = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "DocumentReference")
    assert docref["content"][0]["attachment"]["contentType"] == "application/fhir+json"


def test_export_fhir_excludes_rejected_lines(client):
    encounter, note = _seed_signed_note(client)
    # Sign already happened, so amend to get an editable draft again.
    amended = client.post(f"/encounters/{encounter['id']}/notes/amend").json()
    plan_line = next(l for l in amended["lines"] if l["section"] == "plan")
    client.post(f"/encounters/{encounter['id']}/notes/{amended['id']}/lines/{plan_line['id']}/reject")
    client.post(f"/encounters/{encounter['id']}/notes/{amended['id']}/sign")

    resp = client.post(f"/encounters/{encounter['id']}/notes/{amended['id']}/export-fhir")
    assert resp.status_code == 201
    bundle = resp.json()["bundle"]
    resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert resource_types.count("Observation") == 1  # only the symptom line, plan line was rejected


def test_list_ehr_submissions_returns_prior_exports(client):
    encounter, note = _seed_signed_note(client)
    client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/export-fhir")
    client.post(f"/encounters/{encounter['id']}/notes/{note['id']}/export-fhir")

    resp = client.get(f"/encounters/{encounter['id']}/ehr-submissions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_export_fhir_404_for_note_on_different_encounter(client):
    encounter1, note1 = _seed_signed_note(client)
    encounter2 = client.post("/encounters", json={}).json()

    resp = client.post(f"/encounters/{encounter2['id']}/notes/{note1['id']}/export-fhir")
    assert resp.status_code == 404
