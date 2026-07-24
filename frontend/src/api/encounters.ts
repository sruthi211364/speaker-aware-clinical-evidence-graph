import type {
  Attestation,
  AudioTranscriptionPreview,
  Claim,
  ClaimGraph,
  ClarificationQuestion,
  Encounter,
  GroundingCitation,
  MockEhrSubmission,
  PipelineRunResult,
  PipelineTraceEntry,
  PolicyVerdict,
  SoapNote,
  SpeakerRole,
  TranscribedUtterance,
  TranscriptSegment,
} from '../types/domain'
import { apiClient } from './client'

export async function listEncounters(): Promise<Encounter[]> {
  const res = await apiClient.get('/encounters')
  return res.data
}

export async function createEncounter(): Promise<Encounter> {
  const res = await apiClient.post('/encounters', {})
  return res.data
}

export async function getEncounter(encounterId: string): Promise<Encounter> {
  const res = await apiClient.get(`/encounters/${encounterId}`)
  return res.data
}

export async function listTranscript(encounterId: string): Promise<TranscriptSegment[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/transcript`)
  return res.data
}

export async function listClaims(encounterId: string): Promise<Claim[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/claims`)
  return res.data
}

export async function extractClaims(encounterId: string): Promise<Claim[]> {
  const res = await apiClient.post(`/encounters/${encounterId}/claims/extract`)
  return res.data
}

export async function getClaimGraph(encounterId: string): Promise<ClaimGraph> {
  const res = await apiClient.get(`/encounters/${encounterId}/claim-graph`)
  return res.data
}

export async function buildClaimGraph(encounterId: string): Promise<ClaimGraph['edges']> {
  const res = await apiClient.post(`/encounters/${encounterId}/claim-graph/build`)
  return res.data
}

export async function groundClaims(encounterId: string): Promise<GroundingCitation[]> {
  const res = await apiClient.post(`/encounters/${encounterId}/claims/ground`)
  return res.data
}

export async function getClaimCitations(
  encounterId: string,
  claimId: string,
): Promise<GroundingCitation[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/claims/${claimId}/citations`)
  return res.data
}

export async function runPolicyCheck(encounterId: string): Promise<PolicyVerdict[]> {
  const res = await apiClient.post(`/encounters/${encounterId}/claims/policy-check`)
  return res.data
}

export async function listPolicyVerdicts(encounterId: string): Promise<PolicyVerdict[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/policy-verdicts`)
  return res.data
}

export async function listClarifications(encounterId: string): Promise<ClarificationQuestion[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/clarifications`)
  return res.data
}

export async function answerClarification(
  encounterId: string,
  clarificationId: string,
  answerText: string,
): Promise<ClarificationQuestion> {
  const res = await apiClient.post(`/encounters/${encounterId}/clarifications/${clarificationId}/answer`, {
    answer_text: answerText,
  })
  return res.data
}

export async function normalizeTerminology(encounterId: string): Promise<Claim[]> {
  const res = await apiClient.post(`/encounters/${encounterId}/claims/normalize`)
  return res.data
}

export async function runPipeline(encounterId: string): Promise<PipelineRunResult> {
  const res = await apiClient.post(`/encounters/${encounterId}/pipeline/run`)
  return res.data
}

export async function getPipelineTrace(encounterId: string): Promise<PipelineTraceEntry[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/pipeline/trace`)
  return res.data
}

export async function getPipelineStatus(encounterId: string): Promise<PipelineRunResult> {
  const res = await apiClient.get(`/encounters/${encounterId}/pipeline/status`)
  return res.data
}

export async function resumePipelineReview(encounterId: string): Promise<PipelineRunResult> {
  const res = await apiClient.post(`/encounters/${encounterId}/pipeline/resume-review`)
  return res.data
}

export async function compileSoapNote(encounterId: string): Promise<SoapNote> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/compile`)
  return res.data
}

export async function getLatestSoapNote(encounterId: string): Promise<SoapNote> {
  const res = await apiClient.get(`/encounters/${encounterId}/notes/latest`)
  return res.data
}

export async function acceptNoteLine(
  encounterId: string,
  noteId: string,
  lineId: string,
): Promise<Attestation> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/${noteId}/lines/${lineId}/accept`)
  return res.data
}

export async function editNoteLine(
  encounterId: string,
  noteId: string,
  lineId: string,
  text: string,
): Promise<Attestation> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/${noteId}/lines/${lineId}/edit`, { text })
  return res.data
}

export async function rejectNoteLine(
  encounterId: string,
  noteId: string,
  lineId: string,
): Promise<Attestation> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/${noteId}/lines/${lineId}/reject`)
  return res.data
}

export async function listAttestations(encounterId: string): Promise<Attestation[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/attestations`)
  return res.data
}

export async function signSoapNote(encounterId: string, noteId: string): Promise<SoapNote> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/${noteId}/sign`)
  return res.data
}

export async function amendSoapNote(encounterId: string): Promise<SoapNote> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/amend`)
  return res.data
}

export async function exportNoteToFhir(encounterId: string, noteId: string): Promise<MockEhrSubmission> {
  const res = await apiClient.post(`/encounters/${encounterId}/notes/${noteId}/export-fhir`)
  return res.data
}

export async function listEhrSubmissions(encounterId: string): Promise<MockEhrSubmission[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/ehr-submissions`)
  return res.data
}

export async function previewAudioTranscript(
  encounterId: string,
  file: File,
): Promise<AudioTranscriptionPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await apiClient.post(`/encounters/${encounterId}/transcript/audio/preview`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function commitAudioTranscript(
  encounterId: string,
  utterances: TranscribedUtterance[],
  speakerRoleMap: Record<string, SpeakerRole>,
): Promise<TranscriptSegment[]> {
  const res = await apiClient.post(`/encounters/${encounterId}/transcript/audio/commit`, {
    utterances,
    speaker_role_map: speakerRoleMap,
  })
  return res.data
}
