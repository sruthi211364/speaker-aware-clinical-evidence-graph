from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.models import Encounter
from app.pipeline.graph import get_pipeline_trace, run_pipeline
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


@router.get("/trace", response_model=list[PipelineTraceEntry])
def get_pipeline_trace_endpoint(encounter: Encounter = Depends(get_encounter_or_404)):
    """Returns the LangGraph checkpointer's node-by-node run history for this
    encounter -- the technical trace behind the pipeline run, independent of
    the clinician-facing attestation trail."""
    return get_pipeline_trace(str(encounter.id))
