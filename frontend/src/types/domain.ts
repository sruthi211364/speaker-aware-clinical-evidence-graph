// Mirrors backend/app/models/enums.py. Kept in sync by hand for now; a
// generated client (e.g. openapi-typescript) would be a reasonable upgrade
// once the API surface stabilizes.

export type EncounterStatus = 'in_progress' | 'drafted' | 'reviewed' | 'signed'

export type SpeakerRole = 'patient' | 'caregiver' | 'clinician' | 'system'

export type ClaimType =
  | 'symptom'
  | 'history'
  | 'medication'
  | 'allergy'
  | 'vital'
  | 'exam_finding'
  | 'assessment'
  | 'plan_item'
  | 'other'

export type SourceType =
  | 'patient_speech'
  | 'caregiver_report'
  | 'clinician_observation'
  | 'ehr_data'
  | 'device_data'
  | 'clinician_judgment'

export type ClaimStatus =
  | 'proposed'
  | 'supported'
  | 'contradicted'
  | 'ambiguous'
  | 'missing_context'
  | 'unsupported'
  | 'unsafe'
  | 'accepted'
  | 'edited'
  | 'rejected'

export interface Encounter {
  id: string
  patient_id: string
  clinician_id: string
  started_at: string
  ended_at: string | null
  status: EncounterStatus
  created_at: string
  updated_at: string
}

export interface TranscriptSegment {
  id: string
  encounter_id: string
  speaker_role: SpeakerRole
  speaker_identifier: string | null
  start_ms: number
  end_ms: number
  text: string
  confidence: number | null
  created_at: string
}

export interface Claim {
  id: string
  encounter_id: string
  text: string
  claim_type: ClaimType
  source_type: SourceType
  source_reference: string | null
  confidence: number
  status: ClaimStatus
  normalized_code_system: string | null
  normalized_code: string | null
  normalized_display: string | null
  created_at: string
  updated_at: string
}

export type EdgeRelation =
  | 'supports'
  | 'contradicts'
  | 'refines'
  | 'duplicates'
  | 'depends_on_temporal_context'

export interface ClaimEdge {
  id: string
  source_claim_id: string
  target_claim_id: string
  relation: EdgeRelation
  rationale: string | null
  confidence: number
  created_at: string
}

export interface ClaimGraph {
  claims: Claim[]
  edges: ClaimEdge[]
}

export type GroundingSourceType = 'guideline' | 'drug_data' | 'prior_encounter' | 'coded_vocabulary'

export interface GroundingCitation {
  id: string
  claim_id: string | null
  source_type: GroundingSourceType
  source_identifier: string | null
  excerpt: string | null
  relevance_score: number
  created_at: string
}

export type PolicyCheckType =
  | 'support'
  | 'contradiction'
  | 'temporal_ambiguity'
  | 'missing_context'
  | 'clinical_safety'

export interface PolicyVerdict {
  id: string
  claim_id: string
  check_type: PolicyCheckType
  passed: boolean
  rationale: string | null
  created_at: string
}

export interface ClarificationQuestion {
  id: string
  encounter_id: string
  triggering_claim_id: string
  question_text: string
  grounding_citation_id: string | null
  resolved: boolean
  resolved_by_claim_id: string | null
  created_at: string
  resolved_at: string | null
}

export interface PipelineRunResult {
  encounter_id: string
  transcript_segment_count: number
  claim_count: number
  edge_count: number
  citation_count: number
  verdict_count: number
  open_clarification_count: number
  normalized_claim_count: number
  note_id: string | null
  note_version: number | null
  awaiting_review: boolean
}

export interface PipelineTraceEntry {
  node: string | null
  step: number | null
  next: string[]
  result: Record<string, unknown> | null
  values: Record<string, unknown>
}

export type SoapSection = 'subjective' | 'objective' | 'assessment' | 'plan'

export type NoteStatus = 'draft' | 'under_review' | 'signed'

export interface SoapNoteLine {
  id: string
  note_id: string
  section: SoapSection
  position: number
  text: string
  is_conflict: boolean
  is_rejected: boolean
  claim_ids: string[]
}

export interface SoapNote {
  id: string
  encounter_id: string
  version: number
  status: NoteStatus
  signed_by: string | null
  signed_at: string | null
  created_at: string
  lines: SoapNoteLine[]
}

export type AttestationAction = 'accepted' | 'edited' | 'rejected' | 'added' | 'signed'

export interface Attestation {
  id: string
  encounter_id: string
  note_version_id: string | null
  note_line_id: string | null
  claim_id: string | null
  actor_id: string
  action: AttestationAction
  before_value: string | null
  after_value: string | null
  created_at: string
}

export interface MockEhrSubmission {
  id: string
  encounter_id: string
  note_id: string
  bundle: Record<string, unknown>
  received_at: string
}

export interface TranscribedUtterance {
  speaker_label: string
  start_ms: number
  end_ms: number
  text: string
  confidence: number | null
}

export interface AudioTranscriptionPreview {
  utterances: TranscribedUtterance[]
  speaker_labels: string[]
}
