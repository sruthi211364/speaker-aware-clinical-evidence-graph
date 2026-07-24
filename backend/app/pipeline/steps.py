"""Pipeline step functions, one per pipeline stage (extract claims -> build
graph -> ground claims -> run policy engine -> normalize terminology).
Shared between the individual per-stage REST endpoints (app/api/claims.py,
graph.py, grounding.py, policy.py -- kept for direct/manual triggering and
inspection) and the LangGraph-orchestrated full-pipeline run
(app/pipeline/graph.py, Phase 5). Both callers share this one implementation
so there is exactly one place each stage's logic lives.

Each function takes a DB session and an Encounter and is idempotent per
encounter, matching the behavior the individual endpoints already had.
"""

from sqlalchemy.orm import Session

from app.models import (
    Claim,
    ClaimEdge,
    Encounter,
    GroundingCitation,
    PolicyVerdict,
    SoapNote,
    SoapNoteLine,
    SoapNoteLineClaim,
    TranscriptSegment,
)
from app.models.enums import (
    ClaimStatus,
    ClaimType,
    EdgeRelation,
    GroundingSourceType,
    NoteStatus,
    SoapSection,
    SourceType,
    SpeakerRole,
)
from app.services.claude_service import (
    ClaimForEdgeInput,
    TranscriptSegmentInput,
    extract_claims_from_transcript,
    generate_claim_edges,
)
from app.services.policy_engine import run_policy_engine_for_claim
from app.services.retrieval_service import (
    retrieve_clinical_knowledge,
    retrieve_patient_history,
    retrieve_vocabulary_term,
)

# Which coded vocabulary a claim type normalizes against. plan_item/other have
# no single natural vocabulary and are left uncoded.
_CLAIM_TYPE_TO_CODE_SYSTEM = {
    ClaimType.medication: "RxNorm",
    ClaimType.allergy: "RxNorm",
    ClaimType.vital: "LOINC",
    ClaimType.symptom: "SNOMED",
    ClaimType.history: "SNOMED",
    ClaimType.exam_finding: "SNOMED",
    ClaimType.assessment: "SNOMED",
}

_SPEAKER_TO_SOURCE_TYPE = {
    SpeakerRole.patient: SourceType.patient_speech,
    SpeakerRole.caregiver: SourceType.caregiver_report,
    SpeakerRole.clinician: SourceType.clinician_observation,
}
_EXTRACTABLE_ROLES = set(_SPEAKER_TO_SOURCE_TYPE)
_GROUNDING_TOP_K = 2

# Which SOAP section a claim type belongs in. A simplification of real SOAP
# conventions (e.g. medications/allergies can also read as history) but a
# defensible, documented default for compiling a first draft.
_CLAIM_TYPE_TO_SECTION = {
    ClaimType.symptom: SoapSection.subjective,
    ClaimType.history: SoapSection.subjective,
    ClaimType.other: SoapSection.subjective,
    ClaimType.exam_finding: SoapSection.objective,
    ClaimType.vital: SoapSection.objective,
    ClaimType.assessment: SoapSection.assessment,
    ClaimType.medication: SoapSection.plan,
    ClaimType.allergy: SoapSection.plan,
    ClaimType.plan_item: SoapSection.plan,
}

_SOURCE_LABEL = {
    SourceType.patient_speech: "Patient",
    SourceType.caregiver_report: "Caregiver",
    SourceType.clinician_observation: "Clinician",
    SourceType.ehr_data: "EHR",
    SourceType.device_data: "Device",
    SourceType.clinician_judgment: "Clinician judgment",
}

# Claims in these statuses never reach the note: proposed means it hasn't
# been through the policy engine yet, unsupported/rejected mean it failed or
# was explicitly turned down by a clinician.
_EXCLUDED_FROM_NOTE = {ClaimStatus.proposed, ClaimStatus.unsupported, ClaimStatus.rejected}


def extract_claims_step(db: Session, encounter: Encounter) -> list[Claim]:
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
    result = extract_claims_from_transcript(model_input)

    claims: list[Claim] = []
    for extracted in result.claims:
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


def build_graph_step(db: Session, encounter: Encounter) -> list[ClaimEdge]:
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
        ClaimForEdgeInput(index=i, claim_type=c.claim_type.value, source_type=c.source_type.value, text=c.text)
        for i, c in enumerate(claims)
    ]
    result = generate_claim_edges(model_input)

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


def ground_claims_step(db: Session, encounter: Encounter) -> list[GroundingCitation]:
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    if not claims:
        return []

    already_grounded = {
        row[0]
        for row in db.query(GroundingCitation.claim_id)
        .filter(GroundingCitation.claim_id.in_([c.id for c in claims]))
        .all()
    }
    to_ground = [c for c in claims if c.id not in already_grounded]
    if not to_ground:
        return (
            db.query(GroundingCitation)
            .filter(GroundingCitation.claim_id.in_([c.id for c in claims]))
            .all()
        )

    citations: list[GroundingCitation] = []
    for claim in to_ground:
        for chunk, score in retrieve_clinical_knowledge(db, claim.text, top_k=_GROUNDING_TOP_K):
            source_type = (
                GroundingSourceType.drug_data
                if chunk.category == "drug_interaction"
                else GroundingSourceType.guideline
            )
            citations.append(
                GroundingCitation(
                    claim_id=claim.id,
                    source_type=source_type,
                    source_identifier=chunk.source_identifier,
                    excerpt=chunk.content,
                    relevance_score=score,
                )
            )
        for chunk, score in retrieve_patient_history(db, encounter.patient_id, claim.text, top_k=_GROUNDING_TOP_K):
            citations.append(
                GroundingCitation(
                    claim_id=claim.id,
                    source_type=GroundingSourceType.prior_encounter,
                    source_identifier=chunk.source_encounter_label,
                    excerpt=chunk.content,
                    relevance_score=score,
                )
            )
    db.add_all(citations)
    db.commit()
    for c in citations:
        db.refresh(c)
    return citations


def run_policy_engine_step(db: Session, encounter: Encounter) -> list[PolicyVerdict]:
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    claim_ids = [c.id for c in claims]

    existing = (
        db.query(PolicyVerdict).filter(PolicyVerdict.claim_id.in_(claim_ids)).all() if claim_ids else []
    )
    if existing:
        return existing

    all_verdicts: list[PolicyVerdict] = []
    for claim in claims:
        all_verdicts.extend(run_policy_engine_for_claim(db, claim))
    db.commit()
    for v in all_verdicts:
        db.refresh(v)
    return all_verdicts


def normalize_terminology_step(db: Session, encounter: Encounter) -> list[Claim]:
    """Maps each surviving claim's clinical concept to a RxNorm/SNOMED/LOINC
    code via embedding search over the vocabulary index. Unsupported claims
    are skipped -- they never reach a note, so coding them is wasted work.
    Idempotent per claim (not per encounter): only claims without a code yet
    are processed, so re-running after a clarification answer adds a new
    claim only normalizes that new claim."""
    claims = (
        db.query(Claim)
        .filter(
            Claim.encounter_id == encounter.id,
            Claim.status != ClaimStatus.unsupported,
            Claim.normalized_code.is_(None),
        )
        .all()
    )

    normalized: list[Claim] = []
    for claim in claims:
        code_system = _CLAIM_TYPE_TO_CODE_SYSTEM.get(claim.claim_type)
        if code_system is None:
            continue
        result = retrieve_vocabulary_term(db, code_system, claim.text)
        if result is None:
            continue
        term, _score = result
        claim.normalized_code_system = term.code_system
        claim.normalized_code = term.code
        claim.normalized_display = term.display
        normalized.append(claim)

    db.commit()
    for c in normalized:
        db.refresh(c)
    return normalized


def _populate_note_lines(db: Session, note: SoapNote, encounter: Encounter) -> None:
    """Builds this note's lines from the encounter's current claims: one
    line per claim, grouped into subjective/objective/assessment/plan.
    Contradicted claims are never silently resolved into a single statement
    -- each contradicting pair becomes one conflict line showing both sides
    with their sources. Shared by compile_soap_note_step (first version) and
    create_next_note_version_step (an amendment after signing)."""
    claims = db.query(Claim).filter_by(encounter_id=encounter.id).order_by(Claim.created_at).all()
    eligible = [c for c in claims if c.status not in _EXCLUDED_FROM_NOTE]
    eligible_ids = {c.id for c in eligible}
    claims_by_id = {c.id: c for c in eligible}

    contradicts_edges = (
        db.query(ClaimEdge)
        .filter(
            ClaimEdge.relation == EdgeRelation.contradicts,
            ClaimEdge.source_claim_id.in_(eligible_ids),
            ClaimEdge.target_claim_id.in_(eligible_ids),
        )
        .all()
        if eligible_ids
        else []
    )

    positions = {section: 0 for section in SoapSection}

    def add_line(section: SoapSection, text: str, is_conflict: bool, claim_ids: list) -> None:
        line = SoapNoteLine(
            note_id=note.id,
            section=section,
            position=positions[section],
            text=text,
            is_conflict=is_conflict,
        )
        positions[section] += 1
        db.add(line)
        db.flush()
        for claim_id in claim_ids:
            db.add(SoapNoteLineClaim(line_id=line.id, claim_id=claim_id))

    claims_in_conflicts: set = set()
    for edge in contradicts_edges:
        source = claims_by_id.get(edge.source_claim_id)
        target = claims_by_id.get(edge.target_claim_id)
        if source is None or target is None:
            continue
        if source.id in claims_in_conflicts or target.id in claims_in_conflicts:
            continue  # already covered by another conflict edge
        text = (
            f"{_SOURCE_LABEL[source.source_type]}: {source.text} "
            f"-- vs -- "
            f"{_SOURCE_LABEL[target.source_type]}: {target.text}"
        )
        section = _CLAIM_TYPE_TO_SECTION.get(source.claim_type, SoapSection.subjective)
        add_line(section, text, True, [source.id, target.id])
        claims_in_conflicts.add(source.id)
        claims_in_conflicts.add(target.id)

    for claim in eligible:
        if claim.id in claims_in_conflicts:
            continue
        section = _CLAIM_TYPE_TO_SECTION.get(claim.claim_type, SoapSection.subjective)
        needs_attribution = claim.source_type in (
            SourceType.patient_speech,
            SourceType.caregiver_report,
            SourceType.clinician_judgment,
        )
        text = f"{_SOURCE_LABEL[claim.source_type]}: {claim.text}" if needs_attribution else claim.text
        add_line(section, text, False, [claim.id])


def compile_soap_note_step(db: Session, encounter: Encounter) -> SoapNote:
    """Compiles surviving claims into version 1 of the encounter's SOAP
    note. Idempotent per encounter: once any note exists, recompiling
    returns the latest version unchanged. A clinician's in-progress review
    is a live, editable draft (see the /notes/{id}/lines/... accept|edit|
    reject endpoints) -- it is never silently regenerated out from under
    them by a later pipeline run. To pick up claims that changed after a
    note was signed, see create_next_note_version_step."""
    existing = (
        db.query(SoapNote)
        .filter_by(encounter_id=encounter.id)
        .order_by(SoapNote.version.desc())
        .first()
    )
    if existing:
        return existing

    note = SoapNote(encounter_id=encounter.id, version=1, status=NoteStatus.draft)
    db.add(note)
    db.flush()
    _populate_note_lines(db, note, encounter)
    db.commit()
    db.refresh(note)
    return note


def create_next_note_version_step(db: Session, encounter: Encounter) -> SoapNote:
    """Starts a new draft version of the note, recompiled fresh from the
    encounter's current claims -- the only way to change a note's content
    once a version has been signed (a signed version is never mutated).
    Requires the latest version to actually be signed; use compile_soap_note
    to create version 1, and the accept/edit/reject endpoints to change an
    unsigned draft in place."""
    latest = (
        db.query(SoapNote)
        .filter_by(encounter_id=encounter.id)
        .order_by(SoapNote.version.desc())
        .first()
    )
    if latest is None or latest.status != NoteStatus.signed:
        raise ValueError("Can only start a new note version once the latest version is signed")

    note = SoapNote(encounter_id=encounter.id, version=latest.version + 1, status=NoteStatus.draft)
    db.add(note)
    db.flush()
    _populate_note_lines(db, note, encounter)
    db.commit()
    db.refresh(note)
    return note
