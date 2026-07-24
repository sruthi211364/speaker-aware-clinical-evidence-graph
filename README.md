# Speaker-Aware Clinical Evidence Graph & SOAP Note System

A clinical documentation system that does not summarize a visit transcript
into a note. Instead it builds a **speaker-aware clinical evidence graph**
during the encounter, decomposes the conversation into atomic clinical
claims, links every claim to its source (patient speech, caregiver report,
clinician observation, EHR data, device data, or explicit clinician
judgment), and compiles the graph into a structured SOAP note only after a
**zero-trust policy engine** has checked every claim for support,
contradiction, temporal ambiguity, missing context, and clinical safety.

Unsupported claims never reach the note. Conflicting accounts from different
speakers stay visible side by side instead of being blended into one
statement. Missing information becomes a targeted clarification question for
the clinician, not a silently generated assumption. Every clinician edit is
stored as a versioned attestation, so there is a full lineage from raw
encounter to signed record.

This is a portfolio/prototype build, developed iteratively phase by phase.
Current status: **Phase 6 of 10 complete** (see [Build phases](#build-phases)).

## Why this exists

Commercial ambient scribes (Abridge, Nuance DAX, Nabla, Suki, Freed, ...)
compete on transcription accuracy and time saved. None of them expose a
claim-level, source-linked evidence graph, and none structurally block an
unsupported statement before it reaches the note. By early 2026 this gap has
produced real, documented failures: fabricated exam findings, hallucinated
history, and a wave of malpractice claims tied to AI-generated note errors --
"draft only" labeling hasn't been enough, because clinicians reviewing under
time pressure still miss subtle inaccuracies.

This project's bet: don't rely on a rushed human review to catch a
hallucination. Block unsupported claims structurally, surface contradictions
instead of resolving them silently, and turn missing information into a
question instead of a guess. This combines two things the market and the
research literature usually keep separate: a **live, speaker-attributed**
evidence graph (most provenance-graph work targets retrospective or
literature-backed reasoning, not a real-time multi-speaker encounter), and a
**policy engine grounded in retrieval** rather than the model's unaided
judgment.

## Architecture

```
Ingestion → Claim extraction → Graph construction → RAG grounding
   → Zero-trust policy engine → Terminology normalization
   → SOAP compilation → Clinician review (human-in-the-loop) → Sign → FHIR export
```

From Phase 5 onward this pipeline is a **LangGraph** state graph
(`backend/app/pipeline/graph.py`): `ingest -> extract_claims -> build_graph
-> ground_claims -> run_policy_engine`, checkpointed to Postgres per encounter
(`thread_id = encounter_id`) via `PostgresSaver`. Every node transition is
persisted, so a run can be inspected step by step after the fact --
`GET /encounters/{id}/pipeline/trace` and the "Audit & Lineage" tab expose
this. Each node is a thin wrapper around the same step functions
(`backend/app/pipeline/steps.py`) that the individual per-stage REST
endpoints call directly, so there is exactly one implementation of each
stage regardless of which entry point triggers it. Phase 7 adds a genuine
`interrupt()` at the clinician review node (the graph pauses and persists
state; the API resumes it exactly where it left off once the clinician acts
-- no polling).

*Implementation note:* the trace endpoint identifies which node produced
each checkpoint by diffing state keys against a fixed key→node map, rather
than trusting LangGraph's checkpoint `tasks`/metadata fields -- those proved
inconsistent about which node they attributed a given checkpoint to across
runs in the installed LangGraph version (1.2.9). Diffing state is fully
deterministic since each node writes a distinct, non-overlapping key.

### Domain model

The claim graph is modeled as plain Postgres rows (`claims` + `claim_edges`)
rather than a dedicated graph database, to keep the stack to one datastore.
A graph database such as Neo4j would be a reasonable upgrade if claim volume
or traversal complexity ever outgrows relational joins.

| Entity | Purpose |
|---|---|
| `Encounter` | One patient visit; status: in_progress → drafted → reviewed → signed |
| `TranscriptSegment` | One speaker-labeled, timestamped utterance |
| `Claim` | One atomic clinical statement, always carrying a `source_type` + `source_reference` |
| `ClaimEdge` | Typed relationship between two claims: supports / contradicts / refines / duplicates / depends_on_temporal_context |
| `SoapNote` / `SoapNoteLine` | A versioned compiled note; every line cites its source claim(s) |
| `ClarificationQuestion` | Generated when the policy engine flags missing context; answering it creates a new claim, never a silent default |
| `Attestation` | Timestamped clinician action (accept/edit/reject/add) forming the audit lineage |
| `GroundingCitation` | Links a claim (or policy verdict, from Phase 5) to a retrieved guideline/drug-data/prior-encounter passage |

### Tech stack

- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic, Postgres + pgvector, Python 3.11
- **Reasoning**: Claude (Anthropic) via structured outputs, orchestrated with LangGraph (from Phase 5)
- **Retrieval**: pgvector for two RAG indexes (clinical knowledge, longitudinal patient history), with local embeddings via `fastembed`/`bge-small-en-v1.5` -- see [deviations](#deviations-from-the-original-brief) below
- **Validation**: Guardrails AI as an independent schema check ahead of the clinical policy engine (from Phase 5)
- **Observability**: Langfuse tracing on every Claude call (from Phase 5)
- **FHIR export**: `fhir.resources` (Composition/Observation/Condition/DocumentReference) (from Phase 8)
- **Frontend**: React + TypeScript + Vite, TanStack Query, React Router, Tailwind v4

## Running it

Requires Docker Desktop.

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY once Phase 2 lands
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: localhost:5433 (user/pass/db: `ceg`/`ceg`/`ceg`)

Seed demo data -- one encounter with a deliberate patient/caregiver timeline
contradiction (exercises Phase 3's contradiction detection), the RAG
knowledge base (guideline snippets, drug interaction facts, and prior
encounter notes for the same demo patient, used for Phase 4 grounding), and
the RxNorm/SNOMED/LOINC vocabulary index (Phase 6 terminology normalization):

```bash
docker compose exec api python -m app.seed
```

The first run downloads the local embedding model (~30MB, cached after) to
embed the knowledge base and vocabulary index -- no API key required for
this step.

### Local (non-Docker) development

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest
```

## Build phases

Each phase lands as a runnable increment; see the repo's task history / commits for what's actually shipped so far.

1. **Scaffold** -- FastAPI, Postgres+pgvector via Docker Compose, all domain models, Alembic migrations, health check, React+TS+Vite shell. ✅ done
2. **Ingestion + claim extraction** -- diarized transcript ingestion, Claude-backed structured claim extraction (`client.messages.parse()` + `output_config.format`), mock EHR context ingestion, transcript + claim list views. ✅ done
3. **Graph construction** -- Claude-backed claim edge generation (supports/contradicts/refines/duplicates/depends_on_temporal_context), claim graph view with contradictions surfaced side by side rather than merged. ✅ done
4. **RAG grounding** -- clinical knowledge index (guideline/documentation-requirement/drug-interaction snippets) + longitudinal patient history index (prior encounter notes), both pgvector-backed with local embeddings; grounding citations retrievable per claim; citation panel in the claim graph view. ✅ done
5. **LangGraph + zero-trust policy engine** -- state graph (ingest -> extract_claims -> build_graph -> ground_claims -> run_policy_engine) with a Postgres checkpointer; 5-part policy engine (support, contradiction, temporal ambiguity, missing context, clinical safety) grounded in Phase 4's retrieved evidence; clarification question generator; run trace endpoint + view; clarification queue with an answer flow that creates a new `clinician_judgment` claim. ✅ done
6. **Terminology normalization** -- pgvector-backed RxNorm/SNOMED CT/LOINC embedding index (a small curated subset, not a full vocabulary download -- see deviations below), wired in as the 6th LangGraph node (`normalize_terminology`, appended after `run_policy_engine`); maps each surviving claim's concept to a code, skipping claims blocked by the support check. ✅ done
7. **SOAP compilation + review workspace** -- LangGraph `interrupt()`-based review node, note editor with accept/edit/reject + attestations.
8. **Signing, versioning, FHIR export** -- note versioning, FHIR R4 resources, mock EHR endpoint, audit/lineage view.
9. **Raw audio ingestion** -- `TranscriptionProvider` interface, AssemblyAI Universal 3 Pro + Medical Mode implementation.
10. **Evaluation harness + polish** -- golden dataset, extraction/policy accuracy scoring, seeded demo encounters, this README's walkthrough section, SECURITY.md.

## Deviations from the original brief

- **RAG retrieval layer: direct pgvector queries via SQLAlchemy, not LangChain's `PGVector` vectorstore.** The brief specifies LangChain for the retrieval layer. This build queries `clinical_knowledge_chunks` / `patient_history_chunks` directly with pgvector's `cosine_distance()` operator instead. Reasoning: LangChain's `PGVector` abstraction manages its own storage tables, which would sit awkwardly alongside this project's existing SQLAlchemy domain models (`GroundingCitation` needs to reference retrieved chunks by our own IDs regardless of how the vectorstore is implemented internally), and the retrieval logic here is simple enough (two tables, cosine similarity, optional patient-scoping) that the direct approach is fewer moving parts for a fast-moving prototype. If the retrieval logic grows more complex (hybrid search, re-ranking, multiple retrievers), LangChain's abstractions would earn their keep and this is a reasonable place to introduce them.
- **Local embeddings (`fastembed` / `bge-small-en-v1.5`, 384-dim) instead of a hosted embeddings API.** Anthropic doesn't offer an embeddings endpoint and recommends Voyage AI for production use. This prototype uses a small local ONNX model instead so it doesn't need a second paid API key beyond `ANTHROPIC_API_KEY` -- everything else (claim extraction, edge generation) already depends on Claude, and requiring a second vendor's credits just to demo grounding felt like unnecessary friction for a portfolio build. Swapping in Voyage AI (or any other embeddings provider) later is a small, isolated change confined to `app/services/embedding_service.py`.
- **Policy engine calls the Claude service module directly, not via a LangChain chain/runnable.** `langchain-core` is present only as `langgraph`'s own transitive dependency (message/state types); the full `langchain` package is unused. Same reasoning as the retrieval-layer deviation above -- one fewer abstraction layer between the policy engine and the exact structured-output contract it needs.
- **Vocabulary index (Phase 6) is a small curated subset (~20 terms), not a real RxNorm/SNOMED CT/LOINC download.** These are large, licensed terminologies (RxNorm and SNOMED CT in particular require UMLS/SNOMED International licensing) unsuitable for bundling into a portfolio prototype. The seeded codes are well-known concept IDs that appear throughout public FHIR examples and clinical terminology tutorials, chosen to cover this build's demo scenarios (chest pain, penicillin allergy, vitals); verify against an authoritative source before any real use. The normalization mechanism itself (embedding search + code system routing by claim type) is the same approach a real deployment would use against the full terminologies.

## Known limitations (by design, for this prototype)

- No production ASR/diarization engine is built from scratch; Phase 9 wraps AssemblyAI behind a `TranscriptionProvider` interface so it's swappable.
- No live EHR integration -- FHIR export posts to a mock receiving endpoint.
- No HIPAA-grade hosting, SOC 2, or FDA pathway -- see `SECURITY.md` for what a real deployment would still need.
- LangGraph's Postgres checkpointer preserves state across the clinician-review pause, but is **not** full durable execution across process crashes. Acceptable for this prototype; a layer like the Temporal LangGraph plugin would close that gap in production.

## Prior art

This project's evidence-graph concept is closely related to (and indebted
to) recent work on evidence-traceable temporal knowledge graphs for
clinical/literature reasoning, provenance graphs from computational biology,
and graph-database architectures for tumor-board EHR review -- all of which
validate the graph-based, source-faithful approach at a systems level, but
applied to retrospective or literature-backed reasoning rather than a live,
multi-speaker encounter. See the phase-10 write-up for full citations and a
head-to-head comparison with commercial ambient scribes.
