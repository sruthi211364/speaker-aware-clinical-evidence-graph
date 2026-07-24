import enum


class EncounterStatus(str, enum.Enum):
    in_progress = "in_progress"
    drafted = "drafted"
    reviewed = "reviewed"
    signed = "signed"


class SpeakerRole(str, enum.Enum):
    patient = "patient"
    caregiver = "caregiver"
    clinician = "clinician"
    system = "system"


class ClaimType(str, enum.Enum):
    symptom = "symptom"
    history = "history"
    medication = "medication"
    allergy = "allergy"
    vital = "vital"
    exam_finding = "exam_finding"
    assessment = "assessment"
    plan_item = "plan_item"
    other = "other"


class SourceType(str, enum.Enum):
    patient_speech = "patient_speech"
    caregiver_report = "caregiver_report"
    clinician_observation = "clinician_observation"
    ehr_data = "ehr_data"
    device_data = "device_data"
    clinician_judgment = "clinician_judgment"


class ClaimStatus(str, enum.Enum):
    proposed = "proposed"
    supported = "supported"
    contradicted = "contradicted"
    ambiguous = "ambiguous"
    missing_context = "missing_context"
    unsupported = "unsupported"
    unsafe = "unsafe"
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"


class EdgeRelation(str, enum.Enum):
    supports = "supports"
    contradicts = "contradicts"
    refines = "refines"
    duplicates = "duplicates"
    depends_on_temporal_context = "depends_on_temporal_context"


class SoapSection(str, enum.Enum):
    subjective = "subjective"
    objective = "objective"
    assessment = "assessment"
    plan = "plan"


class NoteStatus(str, enum.Enum):
    draft = "draft"
    under_review = "under_review"
    signed = "signed"


class AttestationAction(str, enum.Enum):
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"
    added = "added"
    signed = "signed"


class GroundingSourceType(str, enum.Enum):
    guideline = "guideline"
    drug_data = "drug_data"
    prior_encounter = "prior_encounter"
    coded_vocabulary = "coded_vocabulary"


class PolicyCheckType(str, enum.Enum):
    support = "support"
    contradiction = "contradiction"
    temporal_ambiguity = "temporal_ambiguity"
    missing_context = "missing_context"
    clinical_safety = "clinical_safety"
