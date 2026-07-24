"""Single isolation point for every Claude API call in this codebase.

All requests use Claude's structured-outputs feature (`output_config.format`
via `client.messages.parse()`) so extraction results are constrained to a
JSON schema at the API level, not just by prompt instructions. Callers get
typed Pydantic models in and out; nothing outside this module touches the
`anthropic` SDK directly, so the model or provider can be swapped later
without touching the pipeline.
"""

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.config import get_settings

ClaimTypeLiteral = Literal[
    "symptom",
    "history",
    "medication",
    "allergy",
    "vital",
    "exam_finding",
    "assessment",
    "plan_item",
    "other",
]


class TranscriptSegmentInput(BaseModel):
    """One transcript segment as fed to the extraction prompt. `index` is the
    only thing the model is allowed to cite back as a claim's source -- it
    must match a real segment we sent, or the claim is dropped post-hoc."""

    index: int
    speaker_role: str
    text: str


class ExtractedClaim(BaseModel):
    text: str = Field(
        description=(
            "A single, normalized atomic clinical fact, e.g. 'patient reports "
            "chest pain started three days ago'. Never combine multiple facts."
        )
    )
    claim_type: ClaimTypeLiteral
    source_segment_index: int = Field(
        description=(
            "0-based index into the provided transcript segment list identifying "
            "exactly which segment this claim came from. Must be one of the "
            "indices given in the prompt -- never invent one."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this is an accurate extraction directly supported by the cited segment.",
    )


class ClaimExtractionResult(BaseModel):
    claims: list[ExtractedClaim]


class ClaudeNotConfiguredError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is unset. Callers should surface this as
    a clean 503, not let the SDK's low-level header-building error bubble up
    as an opaque 500."""


_EXTRACTION_SYSTEM_PROMPT = """You are a clinical claim extraction engine. You will be given a numbered \
list of transcript segments from a clinical encounter, each labeled with the \
speaker's role (patient, caregiver, or clinician) and the segment's index.

Decompose the transcript into atomic clinical claims: single, self-contained \
clinical facts. Each claim must:
- State exactly one fact. Do not combine multiple facts into one claim.
- Be phrased as a normalized clinical statement (e.g. "patient reports chest \
pain started three days ago"), not a direct quote.
- Cite the exact segment index it was extracted from via source_segment_index. \
Never cite an index that was not given to you, and never state a fact that is \
not directly stated or clearly implied by that specific segment.
- Be classified into the single most appropriate claim_type: symptom, history, \
medication, allergy, vital, exam_finding, assessment, plan_item, or other.

Do not extract claims from clinician questions themselves (e.g. "What brings \
you in today?") -- only from statements that assert a clinical fact. Do not \
infer or guess information that was not stated. If a segment contains no \
extractable clinical fact, produce no claim for it."""


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key or None)


def extract_claims_from_transcript(
    segments: list[TranscriptSegmentInput],
) -> ClaimExtractionResult:
    """Extracts atomic claims from a diarized transcript via Claude's
    structured-outputs API. Any claim citing a segment index we didn't send
    is dropped -- the model is never trusted to self-police its own
    citations."""

    if not segments:
        return ClaimExtractionResult(claims=[])

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ClaudeNotConfiguredError(
            "ANTHROPIC_API_KEY is not set -- claim extraction requires a Claude API key."
        )
    client = _get_client()

    transcript_text = "\n".join(f"[{s.index}] ({s.speaker_role}): {s.text}" for s in segments)

    response = client.messages.parse(
        model=settings.claude_model,
        max_tokens=4096,
        thinking={"type": "disabled"},
        system=_EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Transcript segments:\n{transcript_text}"}],
        output_format=ClaimExtractionResult,
    )
    result = response.parsed_output

    valid_indices = {s.index for s in segments}
    result.claims = [c for c in result.claims if c.source_segment_index in valid_indices]
    return result
