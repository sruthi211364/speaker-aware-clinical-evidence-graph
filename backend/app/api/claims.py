from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_encounter_or_404
from app.auth import require_auth
from app.db import get_db
from app.models import Claim, Encounter, TranscriptSegment
from app.models.enums import ClaimStatus, ClaimType, SourceType, SpeakerRole
from app.schemas.claim import ClaimRead, EhrContextIngestRequest
from app.services.claude_service import (
    ClaudeNotConfiguredError,
    TranscriptSegmentInput,
    extract_claims_from_transcript,
)

router = APIRouter(
    prefix="/encounters/{encounter_id}",
    tags=["claims"],
    dependencies=[Depends(require_auth)],
)

_SPEAKER_TO_SOURCE_TYPE = {
    SpeakerRole.patient: SourceType.patient_speech,
    SpeakerRole.caregiver: SourceType.caregiver_report,
    SpeakerRole.clinician: SourceType.clinician_observation,
}

# Only these speaker roles produce claims from speech; "system" segments
# (e.g. ASR artifacts, non-clinical banter markers) are never sent to Claude.
_EXTRACTABLE_ROLES = set(_SPEAKER_TO_SOURCE_TYPE)


@router.post("/claims/extract", response_model=list[ClaimRead], status_code=201)
def extract_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Runs Claude-backed structured claim extraction over this encounter's
    transcript. Idempotent per encounter: if speech-derived claims already
    exist, returns them instead of extracting (and duplicating) again."""
    existing = (
        db.query(Claim)
        .filter(
            Claim.encounter_id == encounter.id,
            Claim.source_type.in_(list(_SPEAKER_TO_SOURCE_TYPE.values())),
        )
        .all()
    )
    if existing:
        return existing

    segments = (
        db.query(TranscriptSegment)
        .filter_by(encounter_id=encounter.id)
        .order_by(TranscriptSegment.start_ms)
        .all()
    )
    extractable = [s for s in segments if s.speaker_role in _EXTRACTABLE_ROLES]

    model_input = [
        TranscriptSegmentInput(index=i, speaker_role=s.speaker_role.value, text=s.text)
        for i, s in enumerate(extractable)
    ]
    try:
        result = extract_claims_from_transcript(model_input)
    except ClaudeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    claims: list[Claim] = []
    for extracted in result.claims:
        # Defense in depth: re-validate here even though the service module
        # already filters -- a claim citing a segment we never sent must
        # never reach the database, regardless of which layer catches it.
        if not (0 <= extracted.source_segment_index < len(extractable)):
            continue
        segment = extractable[extracted.source_segment_index]
        claims.append(
            Claim(
                encounter_id=encounter.id,
                text=extracted.text,
                claim_type=ClaimType(extracted.claim_type),
                source_type=_SPEAKER_TO_SOURCE_TYPE[segment.speaker_role],
                source_reference=str(segment.id),
                confidence=extracted.confidence,
                status=ClaimStatus.proposed,
            )
        )
    db.add_all(claims)
    db.commit()
    for c in claims:
        db.refresh(c)
    return claims


@router.get("/claims", response_model=list[ClaimRead])
def list_claims(
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    return (
        db.query(Claim)
        .filter_by(encounter_id=encounter.id)
        .order_by(Claim.created_at)
        .all()
    )


@router.post("/ehr-context", response_model=list[ClaimRead], status_code=201)
def ingest_ehr_context(
    payload: EhrContextIngestRequest,
    encounter: Encounter = Depends(get_encounter_or_404),
    db: Session = Depends(get_db),
):
    """Mock EHR context (existing conditions, medications, allergies) is
    already structured data, so it becomes claims directly -- no Claude call
    needed, unlike free-text transcript segments."""
    claims = [
        Claim(
            encounter_id=encounter.id,
            text=item.text,
            claim_type=item.claim_type,
            source_type=SourceType.ehr_data,
            source_reference=item.record_id,
            confidence=1.0,
            status=ClaimStatus.proposed,
        )
        for item in payload.items
    ]
    db.add_all(claims)
    db.commit()
    for c in claims:
        db.refresh(c)
    return claims
