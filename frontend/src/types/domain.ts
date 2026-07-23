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
