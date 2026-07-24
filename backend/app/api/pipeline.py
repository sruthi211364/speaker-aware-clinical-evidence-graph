from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.models import Encounter
from app.pipeline.graph import get_pipeline_status, get_pipeline_trace, resume_pipeline_review, run_pipeline
from app.schemas.policy import PipelineRunResult, PipelineTraceEntry
from app.services.claude_service import ClaudeNotConfiguredError

router = APIRouter(
    prefix="/encounters/{encounter_id}/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_auth)],
)


@router.post("/run", response_model=PipelineRunResult, status_code=201)
def run_pipeline_endpoint(encounter: Encounter = Depends(get_encounter_or_404)):
    """Runs the full LangGraph-orchestrated pipeline for this encounter:
    ingest -> extract_claims -> build_graph -> ground_claims ->
    run_policy_engine. Each stage is idempotent, so re-running is safe and
    picks up where a partial run left off (e.g. after adding a new claim
    from an answered clarification). The individual per-stage endpoints
    (POST .../claims/extract, .../claim-graph/build, .../claims/ground,
    .../claims/policy-check) call the exact same step functions and remain
    available for manual, one-stage-at-a-time triggering."""
    try:
        result = run_pipeline(str(encounter.id))
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return PipelineRunResult(encounter_id=str(encounter.id), **{k: v for k, v in result.items() if k != "encounter_id"})


@router.get("/status", response_model=PipelineRunResult)
def get_pipeline_status_endpoint(encounter: Encounter = Depends(get_encounter_or_404)):
    """Cheap read of where this encounter's run currently stands -- in
    particular, whether it is paused at the clinician_review interrupt --
    without invoking any node. Safe to poll from the SOAP note tab."""
    result = get_pipeline_status(str(encounter.id))
    return PipelineRunResult(encounter_id=str(encounter.id), **{k: v for k, v in result.items() if k != "encounter_id"})


@router.post("/resume-review", response_model=PipelineRunResult)
def resume_pipeline_review_endpoint(encounter: Encounter = Depends(get_encounter_or_404)):
    """Resumes the graph past the clinician_review interrupt. Call this once
    the clinician is done acting on the note's lines (accept/edit/reject) --
    those actions are already durably written by the .../notes endpoints;
    this call only unblocks the paused LangGraph run itself."""
    status = get_pipeline_status(str(encounter.id))
    if not status.get("awaiting_review"):
        raise HTTPException(status_code=409, detail="No pending clinician review to resume for this encounter")
    result = resume_pipeline_review(str(encounter.id))
    return PipelineRunResult(encounter_id=str(encounter.id), **{k: v for k, v in result.items() if k != "encounter_id"})


@router.get("/trace", response_model=list[PipelineTraceEntry])
def get_pipeline_trace_endpoint(encounter: Encounter = Depends(get_encounter_or_404)):
    """Returns the LangGraph checkpointer's node-by-node run history for this
    encounter -- the technical trace behind the pipeline run, independent of
    the clinician-facing attestation trail."""
    return get_pipeline_trace(str(encounter.id))
