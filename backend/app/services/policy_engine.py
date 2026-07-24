"""The zero-trust policy engine: five checks run against every claim before
it's trusted. Support is a hard-coded rule; contradiction is part rule (an
existing contradicts edge) and part Claude-assisted (does the claim conflict
with retrieved patient history); temporal ambiguity, missing context, and
clinical safety are Claude-assisted and grounded strictly in the citations
retrieved in Phase 4 -- never the model's unaided judgment.

A failed check updates the claim's status. Unsupported claims are meant to
never reach a compiled note (Phase 7); contradicted claims stay visible as
separate, attributed statements rather than being merged; a failed
missing-context check produces a ClarificationQuestion instead of letting
the model silently fill the gap.
"""

from sqlalchemy.orm import Session

from app.models import Claim, ClaimEdge, ClarificationQuestion, GroundingCitation, PolicyVerdict
from app.models.enums import ClaimStatus, EdgeRelation, GroundingSourceType, PolicyCheckType
from app.services.claude_service import GroundedEvidenceInput, run_policy_checks


def derive_claim_status(
    *, safety_passed: bool, contradiction_passed: bool, missing_context_passed: bool, temporal_passed: bool
) -> ClaimStatus:
    """The precedence a claim's final status follows once all four
    non-support checks have a result: clinical safety is the most urgent
    finding clinically, so it takes precedence if more than one check
    fails. Pulled out as its own function so the eval harness
    (backend/eval/run_eval.py) scores against the exact same logic this
    engine runs, not a separate reimplementation that could drift from it.
    """
    if not safety_passed:
        return ClaimStatus.unsafe
    if not contradiction_passed:
        return ClaimStatus.contradicted
    if not missing_context_passed:
        return ClaimStatus.missing_context
    if not temporal_passed:
        return ClaimStatus.ambiguous
    return ClaimStatus.supported


def run_policy_engine_for_claim(db: Session, claim: Claim) -> list[PolicyVerdict]:
    verdicts: list[PolicyVerdict] = []

    # 1. Support check -- hard rule, no Claude call. A claim with no source
    # reference has nothing to ground the remaining checks in either, so it
    # short-circuits here.
    support_passed = bool(claim.source_reference)
    verdicts.append(
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.support,
            passed=support_passed,
            rationale=None if support_passed else "Claim has no source reference.",
        )
    )
    if not support_passed:
        claim.status = ClaimStatus.unsupported
        db.add_all(verdicts)
        return verdicts

    # 2a. Structural contradiction -- hard rule from Phase 3's claim edges.
    structural_contradiction = (
        db.query(ClaimEdge)
        .filter(
            ClaimEdge.relation == EdgeRelation.contradicts,
            (ClaimEdge.source_claim_id == claim.id) | (ClaimEdge.target_claim_id == claim.id),
        )
        .first()
        is not None
    )

    citations = db.query(GroundingCitation).filter_by(claim_id=claim.id).all()
    evidence = [
        GroundedEvidenceInput(
            source_type=c.source_type.value,
            source_identifier=c.source_identifier or "unknown",
            excerpt=c.excerpt or "",
        )
        for c in citations
    ]

    check_result = run_policy_checks(claim.text, evidence)

    # 2b. Semantic contradiction vs. longitudinal history -- Claude-assisted.
    contradiction_passed = not (structural_contradiction or check_result.contradicts_history)
    if structural_contradiction and check_result.contradicts_history:
        contradiction_rationale = (
            "Conflicts with another claim from a different source in this encounter, and "
            f"with prior history: {check_result.contradicts_history_rationale}"
        )
    elif structural_contradiction:
        contradiction_rationale = "Conflicts with another claim from a different source in this encounter."
    elif check_result.contradicts_history:
        contradiction_rationale = check_result.contradicts_history_rationale
    else:
        contradiction_rationale = None

    verdicts.append(
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.contradiction,
            passed=contradiction_passed,
            rationale=contradiction_rationale,
        )
    )

    # 3. Temporal ambiguity -- Claude-assisted.
    temporal_passed = not check_result.temporally_ambiguous
    verdicts.append(
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.temporal_ambiguity,
            passed=temporal_passed,
            rationale=check_result.temporal_ambiguity_rationale,
        )
    )

    # 4. Missing context -- Claude-assisted, grounded in the retrieved
    # documentation-standard citation.
    missing_context_passed = not check_result.missing_context
    verdicts.append(
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.missing_context,
            passed=missing_context_passed,
            rationale=check_result.missing_context_rationale,
        )
    )

    # 5. Clinical safety -- Claude-assisted, grounded in the retrieved
    # drug-interaction/allergy citation.
    safety_passed = not check_result.clinical_safety_flag
    verdicts.append(
        PolicyVerdict(
            claim_id=claim.id,
            check_type=PolicyCheckType.clinical_safety,
            passed=safety_passed,
            rationale=check_result.clinical_safety_rationale,
        )
    )

    db.add_all(verdicts)

    claim.status = derive_claim_status(
        safety_passed=safety_passed,
        contradiction_passed=contradiction_passed,
        missing_context_passed=missing_context_passed,
        temporal_passed=temporal_passed,
    )

    if not missing_context_passed and check_result.clarification_question:
        guideline_citation = next(
            (c for c in citations if c.source_type == GroundingSourceType.guideline), None
        )
        db.add(
            ClarificationQuestion(
                encounter_id=claim.encounter_id,
                triggering_claim_id=claim.id,
                question_text=check_result.clarification_question,
                grounding_citation_id=guideline_citation.id if guideline_citation else None,
            )
        )

    return verdicts
