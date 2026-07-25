# Example output

Real responses pulled straight from the running system against the seeded demo data — not hand-written samples. If you want to see what this actually produces without spinning up Docker yourself, this is it.

- **[`claim_graph.json`](claim_graph.json)** — the contradiction encounter's claim graph: four claims, one `contradicts` edge between the patient's and caregiver's accounts of the same symptom.
- **[`soap_note.json`](soap_note.json)** — the compiled note for that same encounter. Line 1 is the interesting one: the contradicting pair merged into a single labeled conflict line (`is_conflict: true`, two `claim_ids`) instead of one account silently winning.
- **[`pipeline_trace.json`](pipeline_trace.json)** — a full LangGraph run, node by node: `ingest → extract_claims → build_graph → ground_claims → run_policy_engine → normalize_terminology → compile_soap_note → clinician_review`, exactly as checkpointed to Postgres.
- **[`attestation_trail.json`](attestation_trail.json)** — the clinician action log for that same run: an accept, an edit, a reject, and three sign events across note versions.
- **[`fhir_bundle.json`](fhir_bundle.json)** — the FHIR R4B bundle exported for the clinical-safety-flag encounter: a `DocumentReference` wrapping a `Composition`, plus one coded `Observation` per surviving note line.

Regenerate any of these yourself once the stack is running:

```bash
curl -s http://localhost:8000/encounters/{id}/notes/latest \
  -H "Authorization: Bearer dev-local-token" | python -m json.tool
```
