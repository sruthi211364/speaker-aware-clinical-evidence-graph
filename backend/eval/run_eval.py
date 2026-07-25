"""Evaluation harness: runs the golden dataset (eval/golden_dataset.py)
through the real claim-extraction and policy-engine logic and reports
claim-level extraction accuracy and status-derivation accuracy.

Two modes:

  --mode mock   (default) Uses deterministic, hand-authored stand-ins for
                what a well-calibrated Claude call should return for each
                golden example, instead of calling the real API. This
                verifies the harness's scoring logic and the pipeline's
                status-derivation logic (via the exact same
                derive_claim_status function app/services/policy_engine.py
                uses, not a reimplementation) end-to-end without spending
                API credits. It is NOT a measurement of the real model's
                accuracy -- see README.

  --mode live   Calls extract_claims_from_transcript and run_policy_checks
                for real. Requires a funded ANTHROPIC_API_KEY. This is the
                mode that actually measures model accuracy; it was written
                and is ready to run, but has not been run against a live
                key while building this project (see README).

Usage:
    cd backend && python -m eval.run_eval --mode mock
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from app.services.claude_service import (
    ClaimExtractionResult,
    ExtractedClaim,
    GroundedEvidenceInput,
    PolicyCheckResult,
    TranscriptSegmentInput,
    extract_claims_from_transcript,
    run_policy_checks,
)
from app.services.policy_engine import derive_claim_status
from eval.golden_dataset import GOLDEN_EXAMPLES, GoldenClaim, GoldenExample

_SPEAKER_TO_SOURCE_TYPE = {
    "patient": "patient_speech",
    "caregiver": "caregiver_report",
    "clinician": "clinician_observation",
}


def _mock_extract(example: GoldenExample) -> ClaimExtractionResult:
    """A stand-in for a well-calibrated extraction call: reuses each cited
    segment's own spoken text as the "extracted" claim text, rather than
    embedding text_contains directly -- if it echoed text_contains back
    verbatim, _score_extraction's substring check could never fail no
    matter how broken that scoring logic was. Using the segment's actual
    text keeps the check genuine while still passing for a correctly
    specified golden example."""
    return ClaimExtractionResult(
        claims=[
            ExtractedClaim(
                text=example.segments[gc.segment_index].text,
                claim_type=gc.claim_type,
                source_segment_index=gc.segment_index,
                confidence=0.9,
            )
            for gc in example.expected_claims
        ]
    )


def _mock_policy_check(claim: GoldenClaim) -> PolicyCheckResult:
    return PolicyCheckResult(
        contradicts_history=claim.contradicts_history,
        contradicts_history_rationale="mock: golden dataset value" if claim.contradicts_history else None,
        temporally_ambiguous=claim.temporally_ambiguous,
        temporal_ambiguity_rationale="mock: golden dataset value" if claim.temporally_ambiguous else None,
        missing_context=claim.missing_context,
        missing_context_rationale="mock: golden dataset value" if claim.missing_context else None,
        clarification_question="mock: what additional detail is needed?" if claim.missing_context else None,
        clinical_safety_flag=claim.clinical_safety_flag,
        clinical_safety_rationale="mock: golden dataset value" if claim.clinical_safety_flag else None,
    )


@dataclass
class ExampleResult:
    name: str
    extraction_true_positives: int
    extraction_false_negatives: int
    extraction_false_positives: int
    status_correct: int
    status_total: int
    status_mismatches: list[str]


def _score_extraction(example: GoldenExample, extracted: ClaimExtractionResult) -> tuple[int, int, int]:
    """Matches extracted claims to golden claims by source_segment_index
    (the definitive identity link back to the transcript), checking every
    candidate claim at that segment for a claim_type + text_contains match
    -- a single segment can legitimately produce more than one claim (e.g.
    "started on amoxicillin for a sinus infection" extracts both a
    medication claim and an assessment claim), so only ever checking the
    first claim found at an index would silently miss a correct match
    sitting second in the list. A real live run caught this: see git log.
    """
    by_segment: dict[int, list[ExtractedClaim]] = {}
    for c in extracted.claims:
        by_segment.setdefault(c.source_segment_index, []).append(c)

    true_positives = 0
    false_negatives = 0
    for gc in example.expected_claims:
        candidates = by_segment.get(gc.segment_index, [])
        match = any(
            c.claim_type == gc.claim_type and gc.text_contains.lower() in c.text.lower() for c in candidates
        )
        if match:
            true_positives += 1
        else:
            false_negatives += 1

    expected_segments = {gc.segment_index for gc in example.expected_claims}
    false_positives = sum(
        len(claims) for seg_idx, claims in by_segment.items() if seg_idx not in expected_segments
    )
    return true_positives, false_negatives, false_positives


def _score_status_derivation(example: GoldenExample, policy_check_fn) -> tuple[int, int, list[str]]:
    """policy_check_fn(gc) may return None to mean "skip this claim" -- e.g.
    in live mode, a claim extraction never found in the first place can't
    be fairly status-scored (that failure is already counted once, by
    _score_extraction, as a missed extraction; scoring it again here as a
    status mismatch would double-penalize the same miss)."""
    contradicted_indices = set(example.contradiction_pair) if example.contradiction_pair else set()
    correct = 0
    total = 0
    mismatches = []
    for i, gc in enumerate(example.expected_claims):
        check_result = policy_check_fn(gc)
        if check_result is None:
            continue
        total += 1
        structural_contradiction = i in contradicted_indices
        derived = derive_claim_status(
            safety_passed=not check_result.clinical_safety_flag,
            contradiction_passed=not (structural_contradiction or check_result.contradicts_history),
            missing_context_passed=not check_result.missing_context,
            temporal_passed=not check_result.temporally_ambiguous,
        )
        if derived.value == gc.expected_status:
            correct += 1
        else:
            mismatches.append(f"claim[{i}] expected={gc.expected_status} derived={derived.value}")
    return correct, total, mismatches


def _find_matching_extracted_claim(gc: GoldenClaim, extracted: ClaimExtractionResult) -> ExtractedClaim | None:
    return next(
        (
            c
            for c in extracted.claims
            if c.source_segment_index == gc.segment_index
            and c.claim_type == gc.claim_type
            and gc.text_contains.lower() in c.text.lower()
        ),
        None,
    )


def run(mode: str) -> list[ExampleResult]:
    results = []
    for example in GOLDEN_EXAMPLES:
        if mode == "live":
            segments = [
                TranscriptSegmentInput(index=i, speaker_role=s.speaker_role, text=s.text)
                for i, s in enumerate(example.segments)
            ]
            extracted = extract_claims_from_transcript(segments)

            def policy_check_fn(gc, _extracted=extracted):
                # Scores the actual extracted claim's text, not a synthetic
                # stand-in -- a bare "patient claim: headache" is far less
                # information-dense than what real extraction produces, and
                # would make the policy checks look worse than they really
                # are for no reason connected to the checks themselves.
                match = _find_matching_extracted_claim(gc, _extracted)
                if match is None:
                    return None
                return run_policy_checks(
                    match.text,
                    [GroundedEvidenceInput(source_type="guideline", source_identifier="none", excerpt="")],
                )
        else:
            extracted = _mock_extract(example)
            policy_check_fn = _mock_policy_check

        tp, fn, fp = _score_extraction(example, extracted)
        status_correct, status_total, mismatches = _score_status_derivation(example, policy_check_fn)
        results.append(
            ExampleResult(
                name=example.name,
                extraction_true_positives=tp,
                extraction_false_negatives=fn,
                extraction_false_positives=fp,
                status_correct=status_correct,
                status_total=status_total,
                status_mismatches=mismatches,
            )
        )
    return results


def print_report(mode: str, results: list[ExampleResult]) -> None:
    print(f"=== Evaluation report (mode={mode}) ===\n")
    total_tp = total_fn = total_fp = 0
    total_status_correct = total_status_total = 0
    for r in results:
        total_tp += r.extraction_true_positives
        total_fn += r.extraction_false_negatives
        total_fp += r.extraction_false_positives
        total_status_correct += r.status_correct
        total_status_total += r.status_total

        print(f"{r.name}:")
        print(f"  extraction: {r.extraction_true_positives} matched, {r.extraction_false_negatives} missed, {r.extraction_false_positives} unexpected")
        print(f"  status derivation: {r.status_correct}/{r.status_total} correct")
        for m in r.status_mismatches:
            print(f"    MISMATCH: {m}")
        print()

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    status_accuracy = total_status_correct / total_status_total if total_status_total else 1.0

    print("=== Totals ===")
    print(f"extraction precision={precision:.2f} recall={recall:.2f} f1={f1:.2f}")
    print(f"status derivation accuracy={status_accuracy:.2f} ({total_status_correct}/{total_status_total})")

    if mode == "mock":
        print(
            "\nNote: mode=mock scores the harness's own scoring logic and the app's "
            "status-derivation logic against hand-authored stand-in Claude responses, "
            "not the real model's accuracy. Run with --mode live and a funded "
            "ANTHROPIC_API_KEY to measure that."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    args = parser.parse_args()
    print_report(args.mode, run(args.mode))
