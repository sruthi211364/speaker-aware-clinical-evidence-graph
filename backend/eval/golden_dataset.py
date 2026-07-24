"""Golden examples for the evaluation harness (eval/run_eval.py).

Each example pairs a short transcript with the claims -- and each claim's
expected final policy-engine status -- that a well-calibrated run of this
pipeline should produce. Chosen to cover the main scenario types the
zero-trust policy engine exists to catch: a clean supported statement, a
structural contradiction between two speakers, a claim missing required
context, and a clinical safety conflict.

The `temporally_ambiguous` / `missing_context` / `clinical_safety_flag` /
`contradicts_history` fields on GoldenClaim describe what Claude's policy
check *should* return for this claim -- in live mode they're ignored (the
real model call determines these); in mock mode they're used to build the
canned PolicyCheckResult a well-calibrated model call would produce, so the
harness's status-derivation logic can be verified without spending API
credits. See run_eval.py and README.
"""

from dataclasses import dataclass, field


@dataclass
class GoldenSegment:
    speaker_role: str  # "patient" | "caregiver" | "clinician"
    text: str


@dataclass
class GoldenClaim:
    segment_index: int  # which segment this claim should be extracted from
    text_contains: str  # substring (case-insensitive) the extracted claim's text should contain
    claim_type: str
    source_type: str
    expected_status: str  # supported | contradicted | missing_context | unsafe | ambiguous

    temporally_ambiguous: bool = False
    missing_context: bool = False
    clinical_safety_flag: bool = False
    contradicts_history: bool = False


@dataclass
class GoldenExample:
    name: str
    segments: list[GoldenSegment]
    expected_claims: list[GoldenClaim]
    # 0-based indices into expected_claims of the two claims that should end
    # up linked by a structural "contradicts" edge (Phase 3), if any.
    contradiction_pair: tuple[int, int] | None = None


GOLDEN_EXAMPLES: list[GoldenExample] = [
    GoldenExample(
        name="clean_supported_symptom",
        segments=[
            GoldenSegment("clinician", "What brings you in today?"),
            GoldenSegment("patient", "I've had a mild headache for two days, nothing else."),
        ],
        expected_claims=[
            GoldenClaim(
                segment_index=1,
                text_contains="headache",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="supported",
            ),
        ],
    ),
    GoldenExample(
        name="patient_caregiver_contradiction",
        # The caregiver segment names "chest pain" explicitly rather than
        # saying "it" -- mock mode's extraction stand-in uses the segment's
        # raw text with no contextual pronoun resolution, unlike a real
        # Claude call given the full transcript, so an implicit reference
        # here would make text_contains="chest" fail for a reason that has
        # nothing to do with the scoring logic being tested.
        segments=[
            GoldenSegment("patient", "My chest has hurt for three days."),
            GoldenSegment("caregiver", "Actually the chest pain has been going on for a week."),
        ],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="chest",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="contradicted",
            ),
            GoldenClaim(
                segment_index=1,
                text_contains="chest",
                claim_type="symptom",
                source_type="caregiver_report",
                expected_status="contradicted",
            ),
        ],
        contradiction_pair=(0, 1),
    ),
    GoldenExample(
        name="missing_context_symptom",
        segments=[
            GoldenSegment("patient", "I've just been feeling really tired lately."),
        ],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="tired",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="missing_context",
                missing_context=True,
            ),
        ],
    ),
    GoldenExample(
        name="clinical_safety_drug_allergy",
        segments=[
            GoldenSegment("clinician", "I'm going to start you on amoxicillin for that sinus infection."),
        ],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="amoxicillin",
                claim_type="medication",
                source_type="clinician_observation",
                expected_status="unsafe",
                clinical_safety_flag=True,
            ),
        ],
    ),
]
