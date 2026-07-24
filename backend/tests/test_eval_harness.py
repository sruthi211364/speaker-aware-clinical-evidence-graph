"""Tests for the evaluation harness itself (eval/run_eval.py) -- not the
app's pipeline. These exist because a scoring harness that can never fail
is worse than no harness at all: a bug here would silently make every
future accuracy report meaningless. See the mock_extract fix history in
git log for a real example of exactly that kind of bug.
"""

from eval.golden_dataset import GoldenClaim, GoldenExample, GoldenSegment
from eval.run_eval import (
    ClaimExtractionResult,
    ExtractedClaim,
    _mock_policy_check,
    _score_extraction,
    _score_status_derivation,
    run,
)


def test_mock_mode_scores_perfectly_on_the_real_golden_dataset():
    results = run("mock")
    for r in results:
        assert r.extraction_false_negatives == 0, f"{r.name}: missed an expected claim"
        assert r.extraction_false_positives == 0, f"{r.name}: produced an unexpected claim"
        assert r.status_correct == r.status_total, f"{r.name}: {r.status_mismatches}"


def test_score_extraction_catches_a_text_mismatch():
    example = GoldenExample(
        name="t",
        segments=[GoldenSegment("patient", "I have a headache.")],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="this substring is absent",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="supported",
            )
        ],
    )
    extracted = ClaimExtractionResult(
        claims=[ExtractedClaim(text="I have a headache.", claim_type="symptom", source_segment_index=0, confidence=0.9)]
    )
    tp, fn, fp = _score_extraction(example, extracted)
    assert (tp, fn, fp) == (0, 1, 0)


def test_score_extraction_catches_a_claim_type_mismatch():
    example = GoldenExample(
        name="t",
        segments=[GoldenSegment("patient", "I have a headache.")],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="headache",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="supported",
            )
        ],
    )
    extracted = ClaimExtractionResult(
        claims=[ExtractedClaim(text="I have a headache.", claim_type="medication", source_segment_index=0, confidence=0.9)]
    )
    tp, fn, fp = _score_extraction(example, extracted)
    assert (tp, fn, fp) == (0, 1, 0)


def test_score_extraction_catches_an_unexpected_extra_claim():
    example = GoldenExample(
        name="t",
        segments=[GoldenSegment("patient", "I have a headache."), GoldenSegment("patient", "My knee also hurts.")],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="headache",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="supported",
            )
        ],
    )
    extracted = ClaimExtractionResult(
        claims=[
            ExtractedClaim(text="I have a headache.", claim_type="symptom", source_segment_index=0, confidence=0.9),
            ExtractedClaim(text="My knee also hurts.", claim_type="symptom", source_segment_index=1, confidence=0.9),
        ]
    )
    tp, fn, fp = _score_extraction(example, extracted)
    assert (tp, fn, fp) == (1, 0, 1)


def test_score_status_derivation_catches_a_wrong_expected_status():
    example = GoldenExample(
        name="t",
        segments=[GoldenSegment("patient", "I have a headache.")],
        expected_claims=[
            GoldenClaim(
                segment_index=0,
                text_contains="headache",
                claim_type="symptom",
                source_type="patient_speech",
                expected_status="unsafe",  # deliberately wrong -- nothing here should flag as unsafe
            )
        ],
    )
    correct, total, mismatches = _score_status_derivation(example, _mock_policy_check)
    assert correct == 0
    assert total == 1
    assert len(mismatches) == 1
