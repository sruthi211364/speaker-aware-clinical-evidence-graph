from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, ClaimEdge, Encounter
from app.pipeline.steps import build_graph_step
from app.schemas.claim_edge import ClaimEdgeRead, ClaimGraphResponse
from app.services.claude_service import ClaudeNotConfiguredError

router = APIRouter(
    prefix="/encounters/{encounter_id}/claim-graph",
    tags=["claim-graph"],
    dependencies=[Depends(require_auth)],
)


@router.post("/build", response_model=list[ClaimEdgeRead], status_code=201)
def build_claim_graph(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Compares this encounter's claims against each other via Claude to find
    supports/contradicts/refines/duplicates/depends_on_temporal_context
    relationships. Idempotent: if edges already exist for this encounter's
    claims, returns them instead of rebuilding."""
    try:
        return build_graph_step(db, encounter)
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("", response_model=ClaimGraphResponse)
def get_claim_graph(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    claim_ids = [c.id for c in claims]
    edges = (
        db.query(ClaimEdge).filter(ClaimEdge.source_claim_id.in_(claim_ids)).all() if claim_ids else []
    )
    return ClaimGraphResponse(claims=claims, edges=edges)
