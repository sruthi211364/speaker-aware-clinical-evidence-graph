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


EdgeRelationLiteral = Literal[
    "supports",
    "contradicts",
    "refines",
    "duplicates",
    "depends_on_temporal_context",
]


class ClaimForEdgeInput(BaseModel):
    """One claim as fed to the edge-generation prompt. `index` is the only
    thing the model may cite back in an edge -- same never-trust-a-raw-
    citation pattern as claim extraction's source_segment_index."""

    index: int
    claim_type: str
    source_type: str
    text: str


class ExtractedEdge(BaseModel):
    source_claim_index: int = Field(description="Index of the first claim in the relationship.")
    target_claim_index: int = Field(description="Index of the second claim in the relationship.")
    relation: EdgeRelationLiteral
    rationale: str = Field(description="One sentence explaining why these two claims are related this way.")
    confidence: float = Field(ge=0.0, le=1.0)


class EdgeExtractionResult(BaseModel):
    edges: list[ExtractedEdge]


class GroundedEvidenceInput(BaseModel):
    """One retrieved grounding citation as fed to the policy-check prompt --
    the model reasons only over evidence we actually retrieved, never its
    unaided judgment."""

    source_type: str
    source_identifier: str
    excerpt: str


class PolicyCheckResult(BaseModel):
    """The four Claude-assisted policy engine verdicts for one claim (the
    fifth check, support, is a hard-coded rule with no model call -- see
    app/services/policy_engine.py). Each verdict is grounded in the specific
    citations passed in the prompt, never the model's unaided judgment."""

    contradicts_history: bool = Field(
        description="True if this claim conflicts with a retrieved prior-encounter note (e.g. a symptom described differently at a past visit)."
    )
    contradicts_history_rationale: str | None = Field(
        default=None, description="Required if contradicts_history is true; otherwise omit."
    )
    temporally_ambiguous: bool = Field(
        description="True if the claim depends on a time reference that is unclear or missing (e.g. 'a while ago')."
    )
    temporal_ambiguity_rationale: str | None = Field(
        default=None, description="Required if temporally_ambiguous is true; otherwise omit."
    )
    missing_context: bool = Field(
        description="True if, per the retrieved documentation-standard citation, this claim type normally requires additional information that is absent."
    )
    missing_context_rationale: str | None = Field(
        default=None, description="Required if missing_context is true; otherwise omit."
    )
    clarification_question: str | None = Field(
        default=None,
        description="A plain-language question for the clinician, grounded in the documentation-standard citation. Required if missing_context is true; otherwise omit.",
    )
    clinical_safety_flag: bool = Field(
        description="True if, per the retrieved drug-interaction/allergy citation, this claim describes a medication conflicting with a documented allergy or existing prescription."
    )
    clinical_safety_rationale: str | None = Field(
        default=None, description="Required if clinical_safety_flag is true; otherwise omit."
    )


class ClaudeNotConfiguredError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is unset. Callers should surface this as
    a clean 503, not let the SDK's low-level header-building error bubble up
    as an opaque 500."""


class ClaudeRequestError(RuntimeError):
    """Raised when a configured client's request to Claude itself fails --
    insufficient credit balance, rate limiting, an auth rejection, a
    transient API error. Callers should surface this as a clean 502 with the
    underlying message, not let it bubble up as an opaque 500: a generic
    "Extraction failed." with no further detail tells the caller nothing
    about why, or what to do about it."""


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


_EDGE_SYSTEM_PROMPT = """You are a clinical claim graph builder. You will be given a numbered list \
of atomic clinical claims extracted from a single patient encounter, each \
labeled with its claim_type, source_type (who or what it came from -- patient \
speech, caregiver report, clinician observation, or EHR data), and text.

Identify pairs of claims that are meaningfully related and classify the \
relationship as exactly one of:
- contradicts: the two claims describe the same clinical topic but conflict \
(e.g. different onset timelines from different speakers, a symptom described \
present by one source and absent by another).
- supports: the two claims describe the same clinical topic and agree, \
corroborating each other (especially valuable when they come from different \
source_types).
- refines: one claim adds detail or specificity to the other without \
conflicting (e.g. a vague symptom claim followed by a more specific one).
- duplicates: the two claims restate the same fact in different words.
- depends_on_temporal_context: one claim's meaning is ambiguous or incomplete \
without timing information that another claim would supply or that is simply \
missing (e.g. "started a while ago" needs a concrete anchor).

Only propose a pair when the relationship is clinically meaningful -- do not \
force a relationship between unrelated claims. Reference claims only by the \
index numbers given to you; never invent an index. Each pair should appear at \
most once (do not also emit the reverse direction as a separate edge)."""


_POLICY_CHECK_SYSTEM_PROMPT = """You are a clinical policy engine performing four checks on a single \
clinical claim, using ONLY the retrieved evidence provided to you. Never use \
outside knowledge or assumptions -- every verdict must be traceable to a \
specific piece of the evidence given, or must be false/absent.

The evidence is labeled by type: "prior_encounter" (notes from the patient's \
past visits), "guideline" (documentation-standard snippets describing what \
this claim type should normally include), and "drug_data" (drug interaction \
and allergy cross-reactivity facts). Some categories may have no evidence at \
all for this claim -- if so, that check should come back false for lack of \
grounding, not from inference.

Perform exactly these four checks:

1. contradicts_history: Does the claim conflict with a retrieved \
prior_encounter note -- e.g. a symptom described with a different onset, \
severity, or character than at a past visit? Only flag a genuine conflict, \
not a claim that simply isn't mentioned in the prior note.

2. temporally_ambiguous: Does the claim depend on a time reference that is \
vague or missing (e.g. "a while ago", "recently") such that a reader cannot \
tell when the described event happened?

3. missing_context: Per the retrieved guideline citation (if any) describing \
what this claim type should document, is required information absent from \
the claim? If true, you MUST write a clarification_question: a short, plain \
-language question a clinician could ask the patient to fill that specific \
gap, grounded in what the guideline says is required. If there is no \
guideline evidence for this claim type, this check must be false.

4. clinical_safety_flag: Per the retrieved drug_data citation (if any), does \
the claim describe a medication that conflicts with a documented allergy or \
cross-reacts with it? If there is no drug_data evidence, this check must be \
false.

For any check that is true, its *_rationale field is required and must cite \
what in the evidence justifies it. For any check that is false, leave its \
rationale and (for missing_context) clarification_question empty."""


def _require_configured_client(settings) -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise ClaudeNotConfiguredError(
            "ANTHROPIC_API_KEY is not set -- this operation requires a Claude API key."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


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
    client = _require_configured_client(settings)

    transcript_text = "\n".join(f"[{s.index}] ({s.speaker_role}): {s.text}" for s in segments)

    try:
        response = client.messages.parse(
            model=settings.claude_model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Transcript segments:\n{transcript_text}"}],
            output_format=ClaimExtractionResult,
        )
    except anthropic.APIError as exc:
        raise ClaudeRequestError(f"Claim extraction request to Claude failed: {exc}") from exc
    result = response.parsed_output

    valid_indices = {s.index for s in segments}
    result.claims = [c for c in result.claims if c.source_segment_index in valid_indices]
    return result


def generate_claim_edges(claims: list[ClaimForEdgeInput]) -> EdgeExtractionResult:
    """Compares claims against each other via Claude's structured-outputs API
    to find supports/contradicts/refines/duplicates/depends_on_temporal_context
    relationships. Any edge citing an index we didn't send, or a self-loop, is
    dropped post-hoc -- same never-trust-a-raw-citation pattern as extraction."""

    if len(claims) < 2:
        return EdgeExtractionResult(edges=[])

    settings = get_settings()
    client = _require_configured_client(settings)

    claims_text = "\n".join(
        f"[{c.index}] ({c.claim_type} / {c.source_type}): {c.text}" for c in claims
    )

    try:
        response = client.messages.parse(
            model=settings.claude_model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=_EDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Claims:\n{claims_text}"}],
            output_format=EdgeExtractionResult,
        )
    except anthropic.APIError as exc:
        raise ClaudeRequestError(f"Edge generation request to Claude failed: {exc}") from exc
    result = response.parsed_output

    valid_indices = {c.index for c in claims}
    result.edges = [
        e
        for e in result.edges
        if e.source_claim_index in valid_indices
        and e.target_claim_index in valid_indices
        and e.source_claim_index != e.target_claim_index
    ]
    return result


def run_policy_checks(claim_text: str, evidence: list[GroundedEvidenceInput]) -> PolicyCheckResult:
    """Runs the four Claude-assisted policy checks (contradiction-vs-history,
    temporal ambiguity, missing context, clinical safety) for one claim,
    grounded strictly in the retrieved evidence passed in. The fifth check
    (support) is a hard-coded rule -- see app/services/policy_engine.py."""

    settings = get_settings()
    client = _require_configured_client(settings)

    if evidence:
        evidence_text = "\n".join(
            f"- [{e.source_type}] {e.source_identifier}: {e.excerpt}" for e in evidence
        )
    else:
        evidence_text = "(no grounding evidence was retrieved for this claim)"

    prompt = f"Claim: {claim_text}\n\nRetrieved evidence:\n{evidence_text}"

    try:
        response = client.messages.parse(
            model=settings.claude_model,
            max_tokens=2048,
            thinking={"type": "disabled"},
            system=_POLICY_CHECK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format=PolicyCheckResult,
        )
    except anthropic.APIError as exc:
        raise ClaudeRequestError(f"Policy check request to Claude failed: {exc}") from exc
    return response.parsed_output
