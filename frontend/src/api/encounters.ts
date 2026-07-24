import type { Claim, ClaimGraph, Encounter, TranscriptSegment } from '../types/domain'
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
