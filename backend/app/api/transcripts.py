from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.config import get_settings
from app.db import get_db
from app.models import Encounter, TranscriptSegment
from app.schemas.transcript import (
    AudioTranscriptCommitRequest,
    AudioTranscriptionPreview,
    TranscribedUtteranceOut,
    TranscriptIngestRequest,
    TranscriptSegmentRead,
)
from app.services.transcription_service import TranscriptionNotConfiguredError, get_transcription_provider

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


@router.post("/audio/preview", response_model=AudioTranscriptionPreview)
def preview_audio_transcript(
    encounter: Encounter = Depends(get_encounter_or_404),
    file: UploadFile = File(...),
):
    """Transcribes and diarizes a raw audio file via the configured
    TranscriptionProvider (AssemblyAI). Nothing is persisted yet: the result
    carries AssemblyAI's anonymous speaker labels ("A", "B", ...), and there
    is no way to know from audio alone which one is the patient versus the
    clinician. POST the returned utterances to .../transcript/audio/commit
    along with a speaker_role_map to actually create transcript segments."""
    try:
        provider = get_transcription_provider(get_settings())
    except TranscriptionNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    audio_bytes = file.file.read()
    utterances = provider.transcribe(audio_bytes)
    speaker_labels = sorted({u.speaker_label for u in utterances})
    return AudioTranscriptionPreview(
        utterances=[TranscribedUtteranceOut(**u.model_dump()) for u in utterances],
        speaker_labels=speaker_labels,
    )


@router.post("/audio/commit", response_model=list[TranscriptSegmentRead], status_code=201)
def commit_audio_transcript(
    payload: AudioTranscriptCommitRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Creates transcript segments from a previewed audio transcription.
    Every speaker_label present in `utterances` must have an entry in
    speaker_role_map -- an utterance from an unmapped speaker is rejected
    outright rather than silently dropped or guessed at."""
    speaker_labels = {u.speaker_label for u in payload.utterances}
    unmapped = speaker_labels - set(payload.speaker_role_map)
    if unmapped:
        raise HTTPException(
            status_code=422,
            detail=(
                f"speaker_role_map is missing an entry for diarized speaker(s): {sorted(unmapped)}. "
                "Every speaker AssemblyAI detected must be mapped so no utterance is silently dropped."
            ),
        )

    segments = [
        TranscriptSegment(
            encounter_id=encounter.id,
            speaker_role=payload.speaker_role_map[u.speaker_label],
            speaker_identifier=f"assemblyai:{u.speaker_label}",
            start_ms=u.start_ms,
            end_ms=u.end_ms,
            text=u.text,
            confidence=u.confidence,
        )
        for u in payload.utterances
    ]
    db.add_all(segments)
    db.commit()
    for seg in segments:
        db.refresh(seg)
    return segments
