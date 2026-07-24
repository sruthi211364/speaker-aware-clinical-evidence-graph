import type {
  Claim,
  ClaimGraph,
  ClarificationQuestion,
  Encounter,
  GroundingCitation,
  PipelineRunResult,
  PipelineTraceEntry,
  PolicyVerdict,
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

export async function runPipeline(encounterId: string): Promise<PipelineRunResult> {
  const res = await apiClient.post(`/encounters/${encounterId}/pipeline/run`)
  return res.data
}

export async function getPipelineTrace(encounterId: string): Promise<PipelineTraceEntry[]> {
  const res = await apiClient.get(`/encounters/${encounterId}/pipeline/trace`)
  return res.data
}
