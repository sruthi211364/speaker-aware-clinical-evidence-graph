"""The pipeline as a LangGraph state graph: ingest -> extract_claims ->
build_graph -> ground_claims -> run_policy_engine. Each node is a thin
wrapper around the shared step functions in app/pipeline/steps.py, opening
its own short-lived DB session (LangGraph state must stay JSON-serializable
for the checkpointer, so a SQLAlchemy Session can't live in the state
itself).

Checkpointed to Postgres per encounter (thread_id = encounter_id), so a run
can be inspected node-by-node after the fact via get_pipeline_trace -- this
is the technical trace that sits alongside the clinician-facing attestation
trail in the audit view (Phase 8).

Phases 7-9 extend this graph with more nodes appended after run_policy_engine
(terminology normalization, SOAP compilation, the clinician-review
interrupt, signing) rather than replacing it.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.db import SessionLocal
from app.models import ClarificationQuestion, Encounter, TranscriptSegment
from app.pipeline.checkpointer import checkpointer_context
from app.pipeline.steps import build_graph_step, extract_claims_step, ground_claims_step, run_policy_engine_step


class PipelineState(TypedDict):
    encounter_id: str
    transcript_segment_count: int
    claim_count: int
    edge_count: int
    citation_count: int
    verdict_count: int
    open_clarification_count: int


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


def _build_graph(checkpointer):
    builder = StateGraph(PipelineState)
    builder.add_node("ingest", _node_ingest)
    builder.add_node("extract_claims", _node_extract_claims)
    builder.add_node("build_graph", _node_build_graph)
    builder.add_node("ground_claims", _node_ground_claims)
    builder.add_node("run_policy_engine", _node_run_policy_engine)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "extract_claims")
    builder.add_edge("extract_claims", "build_graph")
    builder.add_edge("build_graph", "ground_claims")
    builder.add_edge("ground_claims", "run_policy_engine")
    builder.add_edge("run_policy_engine", END)

    return builder.compile(checkpointer=checkpointer)


def _thread_config(encounter_id: str) -> dict:
    return {"configurable": {"thread_id": str(encounter_id)}}


def run_pipeline(encounter_id: str) -> PipelineState:
    with checkpointer_context() as checkpointer:
        graph = _build_graph(checkpointer)
        return graph.invoke({"encounter_id": str(encounter_id)}, config=_thread_config(encounter_id))


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
