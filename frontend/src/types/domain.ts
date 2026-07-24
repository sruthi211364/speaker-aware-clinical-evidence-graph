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
