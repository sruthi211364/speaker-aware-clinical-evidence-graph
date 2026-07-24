from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, ClaimEdge, Encounter
from app.models.enums import EdgeRelation
from app.schemas.claim_edge import ClaimEdgeRead, ClaimGraphResponse
from app.services.claude_service import (
    ClaimForEdgeInput,
    ClaudeNotConfiguredError,
    generate_claim_edges,
)

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
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    claim_ids = [c.id for c in claims]

    existing = (
        db.query(ClaimEdge).filter(ClaimEdge.source_claim_id.in_(claim_ids)).all() if claim_ids else []
    )
    if existing:
        return existing

    if len(claims) < 2:
        return []

    model_input = [
        ClaimForEdgeInput(
            index=i,
            claim_type=c.claim_type.value,
            source_type=c.source_type.value,
            text=c.text,
        )
        for i, c in enumerate(claims)
    ]

    try:
        result = generate_claim_edges(model_input)
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    edges: list[ClaimEdge] = []
    for extracted in result.edges:
        if not (0 <= extracted.source_claim_index < len(claims)):
            continue
        if not (0 <= extracted.target_claim_index < len(claims)):
            continue
        edges.append(
            ClaimEdge(
                source_claim_id=claims[extracted.source_claim_index].id,
                target_claim_id=claims[extracted.target_claim_index].id,
                relation=EdgeRelation(extracted.relation),
                rationale=extracted.rationale,
                confidence=extracted.confidence,
            )
        )
    db.add_all(edges)
    db.commit()
    for e in edges:
        db.refresh(e)
    return edges


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
