"""Builds a FHIR R4B bundle from a signed SOAP note. R4B (not plain R4) is
what this project's FHIR library actively maintains -- see README
deviations; Composition/Observation/Condition/DocumentReference are
unchanged in content between R4 and R4B, so this is a version-numbering
detail, not a content deviation from the brief.

Only non-rejected lines are exported: a line the clinician rejected during
review never reaches the note's intended audience, and it shouldn't reach
the external record either.

Resources are addressed with bundle-local `urn:uuid:` references rather
than server-assigned FHIR ids, since this bundle is generated standalone and
handed to the mock EHR receiving endpoint in one shot -- not built up
resource-by-resource against a live FHIR server.
"""

import base64
import datetime as dt
import uuid

from fhir.resources.R4B.attachment import Attachment
from fhir.resources.R4B.bundle import Bundle, BundleEntry
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.composition import Composition, CompositionSection
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.documentreference import DocumentReference, DocumentReferenceContent
from fhir.resources.R4B.narrative import Narrative
from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.reference import Reference
from sqlalchemy.orm import Session

from app.models import Encounter, MockEhrSubmission, SoapNote
from app.models.enums import SoapSection

_SECTION_TITLES = {
    SoapSection.subjective: "Subjective",
    SoapSection.objective: "Objective",
    SoapSection.assessment: "Assessment",
    SoapSection.plan: "Plan",
}

_COMPOSITION_TYPE = CodeableConcept(
    coding=[Coding(system="http://loinc.org", code="34109-9", display="Note")]
)


def _urn(resource_id: str) -> str:
    return f"urn:uuid:{resource_id}"


def _narrative(text: str) -> Narrative:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Narrative(status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml">{escaped}</div>')


def _line_coding(line, claims_by_id: dict) -> CodeableConcept | None:
    """Uses the first linked claim that carries a normalized code (RxNorm/
    SNOMED/LOINC, from Phase 6) to code the resource. A conflict line's two
    claims usually share a claim_type/code system; the first is sufficient
    for a single CodeableConcept."""
    for link in line.claim_links:
        claim = claims_by_id.get(link.claim_id)
        if claim and claim.normalized_code_system and claim.normalized_code:
            system = {
                "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "SNOMED": "http://snomed.info/sct",
                "LOINC": "http://loinc.org",
            }.get(claim.normalized_code_system, claim.normalized_code_system)
            return CodeableConcept(
                coding=[Coding(system=system, code=claim.normalized_code, display=claim.normalized_display)],
                text=line.text,
            )
    return CodeableConcept(text=line.text)


def build_fhir_bundle(note: SoapNote, encounter: Encounter, claims_by_id: dict) -> dict:
    """Returns a FHIR Bundle (as a plain JSON-serializable dict) containing
    a Composition, one Observation per subjective/objective/plan line, one
    Condition per assessment line, and a DocumentReference wrapping the
    Composition -- the four resource types the brief asks for."""
    subject_ref = Reference(reference=f"Patient/{encounter.patient_id}")
    author_id = note.signed_by or encounter.clinician_id
    author_ref = Reference(reference=f"Practitioner/{author_id}")
    composed_at = (note.signed_at or note.created_at).replace(tzinfo=dt.timezone.utc).isoformat()

    exported_lines = [line for line in note.lines if not line.is_rejected]

    clinical_entries: list[BundleEntry] = []
    sections: list[CompositionSection] = []

    for section in SoapSection:
        section_lines = sorted(
            (line for line in exported_lines if line.section == section), key=lambda line: line.position
        )
        if not section_lines:
            continue

        section_entries: list[Reference] = []
        for line in section_lines:
            resource_id = str(uuid.uuid4())
            coding = _line_coding(line, claims_by_id)
            if section == SoapSection.assessment:
                resource = Condition(id=resource_id, subject=subject_ref, code=coding)
            else:
                resource = Observation(
                    id=resource_id,
                    status="final",
                    code=coding,
                    subject=subject_ref,
                    valueString=line.text,
                )
            clinical_entries.append(BundleEntry(fullUrl=_urn(resource_id), resource=resource))
            section_entries.append(Reference(reference=_urn(resource_id)))

        sections.append(
            CompositionSection(
                title=_SECTION_TITLES[section],
                text=_narrative("\n".join(line.text for line in section_lines)),
                entry=section_entries or None,
            )
        )

    composition_id = str(uuid.uuid4())
    composition = Composition(
        id=composition_id,
        status="final",
        type=_COMPOSITION_TYPE,
        subject=subject_ref,
        date=composed_at,
        author=[author_ref],
        title=f"SOAP Note -- Encounter {encounter.id} (v{note.version})",
        section=sections,
    )

    docref_id = str(uuid.uuid4())
    composition_json = composition.model_dump_json(exclude_none=True).encode("utf-8")
    document_reference = DocumentReference(
        id=docref_id,
        status="current",
        type=_COMPOSITION_TYPE,
        subject=subject_ref,
        author=[author_ref],
        date=composed_at,
        content=[
            DocumentReferenceContent(
                attachment=Attachment(
                    contentType="application/fhir+json",
                    data=base64.b64encode(composition_json).decode("ascii"),
                )
            )
        ],
    )

    entries = [
        BundleEntry(fullUrl=_urn(docref_id), resource=document_reference),
        BundleEntry(fullUrl=_urn(composition_id), resource=composition),
        *clinical_entries,
    ]
    bundle = Bundle(type="collection", timestamp=composed_at, entry=entries)
    return bundle.model_dump(mode="json", exclude_none=True)


def record_ehr_submission(db: Session, encounter: Encounter, note: SoapNote, bundle: dict) -> MockEhrSubmission:
    """Hands the bundle to the mock EHR receiving endpoint -- stands in for
    a real EHR integration (see README deviations). The full bundle is
    stored verbatim so a submission can be inspected or replayed later
    without recomputing it from the (possibly since-amended) note."""
    submission = MockEhrSubmission(encounter_id=encounter.id, note_id=note.id, bundle=bundle)
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission
