# Speaker-Aware Clinical Evidence Graph & SOAP Note System

**A clinical scribe that would rather ask a question than make one up.**

Most AI scribes take a visit transcript and summarize it into a note in one shot. This one refuses to do that. It first builds a graph of every clinical claim made during the encounter — who actually said it, patient or caregiver or the clinician's own exam — and only lets a claim into the note after it survives a policy engine built to catch the three ways AI notes actually go wrong: inventing something nobody said, quietly picking a side when two people disagree, and papering over a gap with a guess instead of a question.

## What it actually does

- **Every claim has a source.** Patient speech, caregiver report, clinician observation, EHR data, device data — nothing floats free of where it came from.
- **Five checks before anything reaches a note**: is it supported, does it contradict something else, is the timing vague, is required context missing, is it clinically unsafe.
- **Contradictions stay contradictions.** Patient says three days, caregiver says a week — both show up side by side, not blended into one confident sentence.
- **Gaps become questions.** Missing context generates a clarification for the clinician instead of a silent assumption.
- **Every edit is on the record.** Accept, edit, reject, sign — each one is a timestamped attestation, giving a full paper trail from raw transcript to signed note.
- **It actually runs.** Docker Compose, Postgres + pgvector, a real LangGraph pipeline with a genuine human-in-the-loop pause, FHIR export, 64 passing tests. Not a slide deck.

## Why bother

Commercial ambient scribes (Abridge, Nuance DAX, Nabla, Suki, Freed, and the rest) compete on transcription accuracy and time saved. None of them expose a claim-level, source-linked evidence graph, and none structurally block an unsupported statement before it reaches the note. By early 2026 that gap had produced real, documented consequences: fabricated exam findings, hallucinated history, a wave of malpractice claims tied to AI-generated note errors. "Draft only" labeling hasn't been enough, because a clinician reviewing under time pressure still misses subtle inaccuracies.

The bet here is simple: don't rely on a rushed human review to catch a hallucination. Block unsupported claims structurally, surface contradictions instead of resolving them silently, and turn missing information into a question instead of a guess. That combines two things the market and the research literature usually keep separate — a *live, speaker-attributed* evidence graph (most provenance-graph work is retrospective or literature-backed, not a real-time multi-speaker encounter), and a policy engine grounded in retrieval rather than the model's unaided judgment.

## How it works

```
Ingestion → Claim extraction → Graph construction → RAG grounding
   → Zero-trust policy engine → Terminology normalization
   → SOAP compilation → Clinician review (human-in-the-loop) → Sign → FHIR export
```

The whole thing is a **LangGraph** state graph (`backend/app/pipeline/graph.py`), checkpointed to Postgres per encounter, so a run can be replayed node by node after the fact — `GET /encounters/{id}/pipeline/trace` and the "Audit & Lineage" tab both expose this. Every node is a thin wrapper around a shared step function (`backend/app/pipeline/steps.py`), and the individual per-stage REST endpoints call those same functions directly. One implementation per stage, no matter which door you walk in through.

The interesting part is `clinician_review`: it's a genuine LangGraph `interrupt()`. The node calls it, the graph pauses and persists its entire state to Postgres, and there's no polling loop involved — the process can restart and the run resumes exactly where it left off once `POST /encounters/{id}/pipeline/resume-review` sends the signal to continue. The clinician's actual accept/edit/reject actions happen through their own endpoints and write directly to the database, independent of the graph's state — the interrupt is purely a pause point, not a data pipe.

Signing, amending, and exporting to FHIR happen *after* the graph finishes, as their own clinician-triggered actions rather than graph nodes — a note can be amended and re-signed more than once, or exported more than once, and forcing that into a single linear graph run would fight against how review actually happens.

<details>
<summary>A couple of implementation notes, if you're curious</summary>

- The pipeline trace endpoint figures out which node produced a given checkpoint by diffing state keys against a fixed key→node map, rather than trusting LangGraph's own checkpoint metadata — that metadata turned out to be inconsistent about node attribution across runs in the installed LangGraph version (1.2.9). Diffing state is fully deterministic since every node writes a distinct key.
- Re-invoking `POST .../pipeline/run` while the graph is already paused restarts it from the top rather than resuming the interrupt in place. That's safe *only* because every earlier step is idempotent per encounter — the replay is a no-op and the graph lands right back on the same pending review.

</details>

### Data model

The claim graph lives as plain Postgres rows (`claims` + `claim_edges`) rather than a dedicated graph database, to keep the stack to one datastore. If claim volume or traversal complexity ever outgrows relational joins, something like Neo4j would be a reasonable upgrade.

| Entity | What it's for |
|---|---|
| `Encounter` | One patient visit. Status moves `in_progress → drafted → reviewed → signed` |
| `TranscriptSegment` | One speaker-labeled, timestamped utterance |
| `Claim` | One atomic clinical statement, always carrying a source type + reference |
| `ClaimEdge` | A typed relationship between two claims — supports, contradicts, refines, duplicates, depends-on-temporal-context |
| `SoapNote` / `SoapNoteLine` | A versioned compiled note. Signing freezes a version; further changes start a new one rather than mutating a signed record |
| `ClarificationQuestion` | Raised when the policy engine flags missing context. Answering it creates a new claim — never a silent default. Signing is blocked while any of these are open |
| `Attestation` | A timestamped clinician action (accept/edit/reject/add/sign) — the audit lineage |
| `GroundingCitation` | Links a claim to a retrieved guideline, drug-data, or prior-encounter passage |
| `MockEhrSubmission` | One FHIR bundle handed to the mock EHR endpoint, stored verbatim for replay |

### Tech stack

- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic, Postgres + pgvector, Python 3.11
- **Reasoning**: Claude via structured outputs, orchestrated with LangGraph
- **Retrieval**: pgvector across two RAG indexes (clinical knowledge, longitudinal patient history), local embeddings via `fastembed` / `bge-small-en-v1.5`
- **FHIR export**: `fhir.resources` (R4B) building Composition/Observation/Condition/DocumentReference, handed to a mock EHR endpoint
- **ASR**: raw audio behind a small provider interface, AssemblyAI as the only implementation
- **Frontend**: React + TypeScript + Vite, TanStack Query, React Router, Tailwind v4

(A handful of things the original spec named — LangChain, a hosted embeddings API, Guardrails AI, Langfuse — aren't here. See [Where this diverges from the spec](#where-this-diverges-from-the-spec) for the honest reasons why.)

## Running it

Requires Docker Desktop.

```bash
cp .env.example .env        # ANTHROPIC_API_KEY only matters for live extraction — see Take it for a spin, below
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: `localhost:5433` (user/pass/db: `ceg`/`ceg`/`ceg`)

Then seed some demo data:

```bash
docker compose exec api python -m app.seed
```

This creates three encounters, the RAG knowledge base, and the RxNorm/SNOMED/LOINC vocabulary index. Claim extraction and edge generation are the only two steps that genuinely need a live Claude call, so the seed script hand-authors just those two — everything downstream of them (grounding, terminology normalization, SOAP compilation, FHIR export) runs through the real, unmodified application code. What you see is exactly what those code paths produce, not a mockup.

1. **A contradiction, mid-review** — a patient/caregiver timeline conflict, compiled into a note and left unsigned so you can try the review workflow yourself.
2. **A clinical safety flag, signed and exported** — amoxicillin prescribed despite a documented penicillin allergy, carried all the way through signing and a real FHIR export.
3. **Missing context, left open** — a vague symptom report with its clarification question still unanswered. Try signing it.

The first run downloads a small local embedding model (~30MB, cached after that) to embed the knowledge base and vocabulary index.

<details>
<summary>Local (non-Docker) development</summary>

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

</details>

### Tests

```bash
cd backend && pytest
```

### Evaluation harness

```bash
cd backend
python -m eval.run_eval --mode mock   # default, no API key needed
python -m eval.run_eval --mode live   # calls Claude for real, needs a funded ANTHROPIC_API_KEY
```

This runs a small golden dataset through claim extraction and the policy engine's status logic, and reports precision/recall/F1 plus status-accuracy. `--mode live` is the one that actually measures the model's real-world accuracy — it's written and ready to go, but hasn't been run against a funded key while building this (see [limitations](#what-isnt-here-yet)). `--mode mock` scores the same pipeline against hand-authored stand-in responses instead, which at least proves the harness's own scoring logic and the app's status-derivation function are correct without spending a cent.

## Take it for a spin

Everything below works right after `docker compose up --build` + `python -m app.seed` — no API key required.

1. Open http://localhost:5173 and pick the **contradiction, mid-review** encounter. Its **Claim Graph** tab keeps the patient's "three days" and the caregiver's "since last week" side by side under "Conflicting accounts" — never blended into one timeline. Its **SOAP Note** tab shows that same conflict compiled into one labeled line. Try **Edit** to reword it, **Reject** to drop it, then **Sign note**. Check **Audit & Lineage** afterward and you'll find your action sitting right next to the LangGraph trace of how the note got compiled in the first place.
2. Open the **clinical safety flag, signed + exported** encounter. Its **Claim Graph** tab shows the amoxicillin-vs-penicillin-allergy conflict under "Clinical safety flags," grounded in a seeded drug-interaction fact. Click **Export to EHR (FHIR)** again to add a second submission, then look at **Audit & Lineage** for the bundle's resource count and the sign timestamp.
3. Open the **missing context** encounter and check the **Clarifications** tab — the question is still open. Try signing the note and read the error explaining exactly what's blocking it. Answer the clarification and the block clears.
4. Want to see live extraction instead of the seeded stand-ins? Add a funded `ANTHROPIC_API_KEY` to `.env`, restart the `api` container, create a new encounter, add a transcript, and hit **Run full pipeline** from **Audit & Lineage**. It runs the real thing end to end and pauses at the clinician-review interrupt for you to act on. Raw audio upload additionally needs a funded `ASSEMBLYAI_API_KEY`.

Don't want to run any of this yourself? [`examples/`](examples/) has real output pulled straight from the running system — the compiled note with its merged conflict line, a full LangGraph run trace, an exported FHIR bundle, and the attestation trail behind it.

## How it got built

Ten phases, each one a working, tested, committed increment — nothing here is a facade.

| # | Phase |
|---|---|
| 1 | Scaffold: FastAPI + Postgres/pgvector + Docker Compose, full domain model, React/TS/Vite shell |
| 2 | Ingestion + claim extraction: Claude turns transcript segments into atomic, source-cited claims |
| 3 | Claim graph: Claude links claims by relationship (supports/contradicts/refines/duplicates/temporal) |
| 4 | RAG grounding: two pgvector indexes (clinical knowledge, patient history), local embeddings |
| 5 | LangGraph + the policy engine: the pipeline becomes a checkpointed state graph; the 5-check zero-trust engine goes live |
| 6 | Terminology normalization: claims get mapped to RxNorm/SNOMED/LOINC codes |
| 7 | SOAP compilation + review: a real `interrupt()` pauses the graph for a human; note editor with accept/edit/reject |
| 8 | Signing, versioning, FHIR export: sign a note, amend it later, export it to a mock EHR as a FHIR bundle |
| 9 | Raw audio: AssemblyAI-backed transcription with a preview/commit flow so no speaker is ever silently dropped |
| 10 | Eval harness + polish: golden dataset, accuracy scoring, richer seed data, this README |

Full detail lives in the commit history — every phase landed as its own commit with a real "what and why" message, not a squashed dump at the end.

## Where this diverges from the spec

The original brief specified a few particular tools. Some of them didn't make the cut, on purpose:

| The spec asked for | What's here instead | Why |
|---|---|---|
| LangChain's `PGVector` vectorstore | Direct pgvector queries via SQLAlchemy | Two tables and cosine similarity don't need an abstraction layer yet — this is the natural place to add one if retrieval ever gets more complex (hybrid search, re-ranking, multiple retrievers) |
| A hosted embeddings API | Local `fastembed` (`bge-small-en-v1.5`, ONNX, no torch) | Didn't want to require a second paid API key just to demo grounding, on top of the Claude key everything else already needs |
| Policy engine via a LangChain chain | Calls the Claude service module directly | Same reasoning as above — one fewer layer between the engine and the exact structured-output contract it needs |
| A full RxNorm/SNOMED CT/LOINC download | A curated ~20-term subset | These are large, licensed terminologies (UMLS/SNOMED International licensing) that don't belong bundled into a portfolio build. The matching mechanism itself — embedding search, routed by claim type — is the same one a real deployment would run against the full thing |
| Guardrails AI + Langfuse | Neither is wired in | Every Claude call already goes through `client.messages.parse()` against a Pydantic schema, and every model-cited cross-reference gets independently re-validated — that covers Guardrails' job (rejecting malformed output) without an extra dependency. Langfuse's job (call-level tracing) is a genuine, currently-open gap for anyone extending this |
| Plain FHIR R4 | FHIR **R4B** | `fhir.resources` 8.x dropped the plain-R4 namespace in favor of R4B; the four resource types actually used here (Composition/Observation/Condition/DocumentReference) are identical in content between the two |
| AssemblyAI "Universal 3 Pro" + "Medical Mode" | `speech_model="best"` + `speaker_labels` + a boosted clinical vocabulary | That exact branded feature combination isn't part of AssemblyAI's confirmed public API. The provider is fully isolated in one file, so swapping the model string later is a one-line change |

## What isn't here yet

Being upfront about the gaps, because a prototype that pretends to be finished is worse than one that says where it stops:

| Gap | Why it's acceptable for now |
|---|---|
| Raw audio ingestion is only verified against a mocked ASR provider | No funded AssemblyAI key existed while building this. The API/DB wiring is tested end-to-end; what's untested is a real recording's actual transcription quality |
| Uploaded audio is transcribed and immediately discarded | No retention policy is needed yet because nothing is kept — a real deployment handling real recordings would need one |
| "FHIR export" hands off to an in-process function, not a real outbound HTTP call | It stands in for a receiving endpoint. A production build would replace it with a genuine call to the target EHR's API |
| Only four FHIR resource types export (Composition/Observation/Condition/DocumentReference) | Matches what the brief asked for — no `MedicationStatement`, `AllergyIntolerance`, or real `Patient`/`Practitioner` resources yet |
| Signing blocks on unresolved clarifications, but not on unresolved safety flags | Clinicians sometimes knowingly override a safety flag with documented justification, and there's no clean way yet to capture that distinctly from an ordinary edit — so the flag stays visible rather than being a hard, unbypassable block |
| No HIPAA-grade hosting, SOC 2, or FDA review | See `SECURITY.md` for the honest list |
| LangGraph's Postgres checkpointer survives a restart, not full durable execution across a crash | A Temporal-style durable-execution layer would close that specific gap in production |
| SOAP section assignment is a fixed claim-type → section lookup, not clinical judgment | Real SOAP notes are more nuanced than a table (a medication reconciliation, for instance, often belongs in history rather than Plan) |
| Compiling a note is idempotent once per version, not continuously live | A claim that arrives after compilation won't retroactively appear in an unsigned draft — picking it up means signing the current version and starting a new one |
| The eval harness has never scored a real Claude call | No funded key. `--mode mock` proves the scoring logic is correct; it says nothing about the model's actual accuracy, and the golden dataset (4 examples) is small enough that even live numbers wouldn't mean much yet |

## Related work

The evidence-graph idea here is closely related to (and indebted to) recent work on evidence-traceable temporal knowledge graphs for clinical and literature reasoning, provenance graphs from computational biology, and graph-database architectures for tumor-board EHR review. All of that validates the graph-based, source-faithful approach at a systems level — just applied to retrospective or literature-backed reasoning rather than a live, multi-speaker encounter. See [Why bother](#why-bother) above for how this stacks up against the commercial ambient scribes.
