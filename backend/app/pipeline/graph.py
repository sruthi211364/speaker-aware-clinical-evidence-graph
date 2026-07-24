"""The pipeline as a LangGraph state graph: ingest -> extract_claims ->
build_graph -> ground_claims -> run_policy_engine -> normalize_terminology.
Each node is a thin wrapper around the shared step functions in
app/pipeline/steps.py, opening its own short-lived DB session (LangGraph
state must stay JSON-serializable for the checkpointer, so a SQLAlchemy
Session can't live in the state itself).

Checkpointed to Postgres per encounter (thread_id = encounter_id), so a run
can be inspected node-by-node after the fact via get_pipeline_trace -- this
is the technical trace that sits alongside the clinician-facing attestation
trail in the audit view (Phase 8).

Phase 7 extends this graph with compile_soap_note and clinician_review
(a genuine LangGraph interrupt() that pauses the graph -- and persists that
pause to the Postgres checkpointer -- until POST .../pipeline/resume-review
sends a Command(resume=...) to continue it). Re-invoking run_pipeline while
paused restarts the graph from START rather than continuing the interrupt;
that is safe here only because every node's underlying step function is
already idempotent per encounter, so replaying ingest..compile_soap_note is
a no-op and the graph lands back on the same pending interrupt.

Phases 8-9 extend this graph with more nodes appended after
clinician_review (signing) rather than replacing it.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.db import SessionLocal
from app.models import ClarificationQuestion, Encounter, SoapNote, TranscriptSegment
from app.models.enums import EncounterStatus, NoteStatus
from app.pipeline.checkpointer import checkpointer_context
from app.pipeline.steps import (
    build_graph_step,
    compile_soap_note_step,
    extract_claims_step,
    ground_claims_step,
    normalize_terminology_step,
    run_policy_engine_step,
)


class PipelineState(TypedDict):
    encounter_id: str
    transcript_segment_count: int
    claim_count: int
    edge_count: int
    citation_count: int
    verdict_count: int
    open_clarification_count: int
    normalized_claim_count: int
    note_id: str | None
    note_version: int | None
    review_completed: bool
    review_decision: str | None


def _node_ingest(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        count = db.query(TranscriptSegment).filter_by(encounter_id=state["encounter_id"]).count()
        return {"transcript_segment_count": count}
    finally:
        db.close()


def _node_extract_claims(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        claims = extract_claims_step(db, encounter)
        return {"claim_count": len(claims)}
    finally:
        db.close()


def _node_build_graph(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        edges = build_graph_step(db, encounter)
        return {"edge_count": len(edges)}
    finally:
        db.close()


def _node_ground_claims(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        citations = ground_claims_step(db, encounter)
        return {"citation_count": len(citations)}
    finally:
        db.close()


def _node_run_policy_engine(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        verdicts = run_policy_engine_step(db, encounter)
        open_clarifications = (
            db.query(ClarificationQuestion)
            .filter_by(encounter_id=encounter.id, resolved=False)
            .count()
        )
        return {"verdict_count": len(verdicts), "open_clarification_count": open_clarifications}
    finally:
        db.close()


def _node_normalize_terminology(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        normalized = normalize_terminology_step(db, encounter)
        return {"normalized_claim_count": len(normalized)}
    finally:
        db.close()


def _node_compile_soap_note(state: PipelineState) -> dict:
    db = SessionLocal()
    try:
        encounter = db.get(Encounter, state["encounter_id"])
        note = compile_soap_note_step(db, encounter)
        if encounter.status == EncounterStatus.in_progress:
            encounter.status = EncounterStatus.drafted
            db.commit()
        return {"note_id": str(note.id), "note_version": note.version}
    finally:
        db.close()


def _node_clinician_review(state: PipelineState) -> dict:
    # Runs in full from the top both when it first pauses and again when it
    # resumes (LangGraph re-executes the whole node function on resume) --
    # the "mark under_review" write before interrupt() is safe to repeat.
    db = SessionLocal()
    try:
        note = db.get(SoapNote, state["note_id"]) if state.get("note_id") else None
        if note and note.status == NoteStatus.draft:
            note.status = NoteStatus.under_review
            db.commit()

        decision = interrupt(
            {
                "encounter_id": state["encounter_id"],
                "note_id": state.get("note_id"),
                "message": "Compiled SOAP note ready for clinician review.",
            }
        )

        encounter = db.get(Encounter, state["encounter_id"])
        if encounter and encounter.status == EncounterStatus.drafted:
            encounter.status = EncounterStatus.reviewed
            db.commit()
        return {"review_completed": True, "review_decision": str(decision)}
    finally:
        db.close()


def _build_graph(checkpointer):
    builder = StateGraph(PipelineState)
    builder.add_node("ingest", _node_ingest)
    builder.add_node("extract_claims", _node_extract_claims)
    builder.add_node("build_graph", _node_build_graph)
    builder.add_node("ground_claims", _node_ground_claims)
    builder.add_node("run_policy_engine", _node_run_policy_engine)
    builder.add_node("normalize_terminology", _node_normalize_terminology)
    builder.add_node("compile_soap_note", _node_compile_soap_note)
    builder.add_node("clinician_review", _node_clinician_review)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "extract_claims")
    builder.add_edge("extract_claims", "build_graph")
    builder.add_edge("build_graph", "ground_claims")
    builder.add_edge("ground_claims", "run_policy_engine")
    builder.add_edge("run_policy_engine", "normalize_terminology")
    builder.add_edge("normalize_terminology", "compile_soap_note")
    builder.add_edge("compile_soap_note", "clinician_review")
    builder.add_edge("clinician_review", END)

    return builder.compile(checkpointer=checkpointer)


def _thread_config(encounter_id: str) -> dict:
    return {"configurable": {"thread_id": str(encounter_id)}}


def _with_awaiting_review(graph, encounter_id: str, result: dict) -> dict:
    result = dict(result)
    result.pop("__interrupt__", None)
    state = graph.get_state(_thread_config(encounter_id))
    result["awaiting_review"] = "clinician_review" in state.next
    return result


def run_pipeline(encounter_id: str) -> dict:
    """Runs (or resumes progress toward) the full pipeline. If the graph is
    already paused at the clinician_review interrupt for this encounter,
    re-invoking restarts from START -- safe because every earlier step is
    idempotent per encounter, so it lands right back on the same pending
    review rather than duplicating any work."""
    with checkpointer_context() as checkpointer:
        graph = _build_graph(checkpointer)
        result = graph.invoke({"encounter_id": str(encounter_id)}, config=_thread_config(encounter_id))
        return _with_awaiting_review(graph, encounter_id, result)


def resume_pipeline_review(encounter_id: str) -> dict:
    """Sends the clinician's "I'm done reviewing" signal into the paused
    clinician_review node's interrupt(), letting the graph continue past it.
    The clinician's actual accept/edit/reject actions were already written
    directly to the SoapNote/Attestation tables by the dedicated review
    endpoints -- this call only unblocks the graph itself."""
    with checkpointer_context() as checkpointer:
        graph = _build_graph(checkpointer)
        result = graph.invoke(Command(resume={"action": "review_complete"}), config=_thread_config(encounter_id))
        return _with_awaiting_review(graph, encounter_id, result)


def get_pipeline_status(encounter_id: str) -> dict:
    """Cheap read of where this encounter's pipeline run currently stands,
    without invoking any node."""
    with checkpointer_context() as checkpointer:
        graph = _build_graph(checkpointer)
        state = graph.get_state(_thread_config(encounter_id))
        values = dict(state.values)
        values["awaiting_review"] = "clinician_review" in state.next
        return values


# Maps each node's distinctive output key to the node that wrote it, so the
# trace can identify which node ran at each step. Chosen over LangGraph's
# checkpoint `tasks`/metadata fields, whose node-attribution semantics proved
# inconsistent across runs in this LangGraph version -- diffing state keys
# against the compiled graph's own node outputs is fully deterministic.
_STATE_KEY_TO_NODE = {
    "transcript_segment_count": "ingest",
    "claim_count": "extract_claims",
    "edge_count": "build_graph",
    "citation_count": "ground_claims",
    "verdict_count": "run_policy_engine",
    "normalized_claim_count": "normalize_terminology",
    "note_id": "compile_soap_note",
    "review_completed": "clinician_review",
}


def get_pipeline_trace(encounter_id: str) -> list[dict]:
    """Returns the run's node-by-node history, oldest first. Each entry is
    the node that just ran, the state it changed, and the cumulative state
    after it -- this is the technical trace the LangGraph run-trace endpoint
    exposes."""
    with checkpointer_context() as checkpointer:
        graph = _build_graph(checkpointer)
        history = list(graph.get_state_history(_thread_config(encounter_id)))
        trace = []
        prev_values: dict = {}
        for snapshot in reversed(history):
            values = dict(snapshot.values)
            delta = {k: v for k, v in values.items() if prev_values.get(k) != v}
            node = next((n for key, n in _STATE_KEY_TO_NODE.items() if key in delta), None)
            trace.append(
                {
                    "node": node,
                    "step": snapshot.metadata.get("step"),
                    "next": list(snapshot.next),
                    "result": delta or None,
                    "values": values,
                }
            )
            prev_values = values
        return trace
