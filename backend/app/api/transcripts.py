from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Encounter, TranscriptSegment
from app.schemas.transcript import TranscriptIngestRequest, TranscriptSegmentRead

router = APIRouter(
    prefix="/encounters/{encounter_id}/transcript",
    tags=["transcript"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=list[TranscriptSegmentRead], status_code=201)
def ingest_transcript(
    payload: TranscriptIngestRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Accepts an already-diarized transcript (speaker-labeled, timestamped
    segments) -- the primary ingestion path. Raw audio transcription is a
    separate provider behind TranscriptionProvider, added in Phase 9."""
    segments = [
        TranscriptSegment(encounter_id=encounter.id, **seg.model_dump())
        for seg in payload.segments
    ]
    db.add_all(segments)
    db.commit()
    for seg in segments:
        db.refresh(seg)
    return segments


@router.get("", response_model=list[TranscriptSegmentRead])
def list_transcript(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    return (
        db.query(TranscriptSegment)
        .filter_by(encounter_id=encounter.id)
        .order_by(TranscriptSegment.start_ms)
        .all()
    )
