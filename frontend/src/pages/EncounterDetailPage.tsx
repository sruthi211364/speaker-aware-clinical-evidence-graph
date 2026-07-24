import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  buildClaimGraph,
  extractClaims,
  getClaimGraph,
  groundClaims,
  listTranscript,
  normalizeTerminology,
  runPolicyCheck,
} from '../api/encounters'
import AttestationTrail from '../components/AttestationTrail'
import AudioUploadPanel from '../components/AudioUploadPanel'
import ClaimGraphView from '../components/ClaimGraphView'
import ClarificationQueue from '../components/ClarificationQueue'
import PipelineTraceView from '../components/PipelineTraceView'
import SoapNoteView from '../components/SoapNoteView'
import TranscriptView from '../components/TranscriptView'

const TABS = ['Transcript', 'Claim Graph', 'SOAP Note', 'Clarifications', 'Audit & Lineage'] as const
type Tab = (typeof TABS)[number]

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

export default function EncounterDetailPage() {
  const { encounterId } = useParams<{ encounterId: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('Transcript')
  const queryClient = useQueryClient()

  const transcriptQuery = useQuery({
    queryKey: ['transcript', encounterId],
    queryFn: () => listTranscript(encounterId!),
    enabled: !!encounterId,
  })

  const graphQuery = useQuery({
    queryKey: ['claim-graph', encounterId],
    queryFn: () => getClaimGraph(encounterId!),
    enabled: !!encounterId,
  })

  const extractMutation = useMutation({
    mutationFn: () => extractClaims(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
    },
  })

  const buildGraphMutation = useMutation({
    mutationFn: () => buildClaimGraph(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
    },
  })

  const groundMutation = useMutation({
    mutationFn: () => groundClaims(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claim-citations', encounterId] })
    },
  })

  const policyCheckMutation = useMutation({
    mutationFn: () => runPolicyCheck(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['policy-verdicts', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['clarifications', encounterId] })
    },
  })

  const normalizeMutation = useMutation({
    mutationFn: () => normalizeTerminology(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
    },
  })

  return (
    <div className="mx-auto max-w-5xl p-8">
      <Link to="/" className="text-sm text-indigo-600 hover:underline">
        ← Back to encounters
      </Link>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900">
        Encounter {encounterId?.slice(0, 8)}
      </h1>

      <div className="mt-6 flex gap-2 border-b border-slate-200">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-2 text-sm ${
              tab === activeTab
                ? 'border-b-2 border-indigo-600 font-medium text-indigo-600'
                : 'text-slate-400 hover:text-slate-600'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {activeTab === 'Transcript' && (
          <>
            <AudioUploadPanel encounterId={encounterId!} />
            {transcriptQuery.isLoading && <p className="text-sm text-slate-500">Loading transcript...</p>}
            {transcriptQuery.data && <TranscriptView segments={transcriptQuery.data} />}
          </>
        )}

        {activeTab === 'Claim Graph' && (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Claims grouped with their supports/contradicts/refines relationships. Contradicted claims
                stay visible side by side instead of being blended.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => extractMutation.mutate()}
                  disabled={extractMutation.isPending}
                  className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {extractMutation.isPending ? 'Extracting...' : 'Extract claims'}
                </button>
                <button
                  type="button"
                  onClick={() => buildGraphMutation.mutate()}
                  disabled={buildGraphMutation.isPending}
                  className="rounded-md border border-indigo-600 px-3 py-1.5 text-sm font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-50"
                >
                  {buildGraphMutation.isPending ? 'Building...' : 'Build graph'}
                </button>
                <button
                  type="button"
                  onClick={() => groundMutation.mutate()}
                  disabled={groundMutation.isPending}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {groundMutation.isPending ? 'Grounding...' : 'Ground claims'}
                </button>
                <button
                  type="button"
                  onClick={() => policyCheckMutation.mutate()}
                  disabled={policyCheckMutation.isPending}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {policyCheckMutation.isPending ? 'Checking...' : 'Run policy check'}
                </button>
                <button
                  type="button"
                  onClick={() => normalizeMutation.mutate()}
                  disabled={normalizeMutation.isPending}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {normalizeMutation.isPending ? 'Coding...' : 'Normalize terminology'}
                </button>
              </div>
            </div>
            {extractMutation.isError && (
              <p className="mb-3 text-sm text-red-600">{errorDetail(extractMutation.error, 'Extraction failed.')}</p>
            )}
            {buildGraphMutation.isError && (
              <p className="mb-3 text-sm text-red-600">
                {errorDetail(buildGraphMutation.error, 'Graph construction failed.')}
              </p>
            )}
            {groundMutation.isError && (
              <p className="mb-3 text-sm text-red-600">{errorDetail(groundMutation.error, 'Grounding failed.')}</p>
            )}
            {policyCheckMutation.isError && (
              <p className="mb-3 text-sm text-red-600">
                {errorDetail(policyCheckMutation.error, 'Policy check failed.')}
              </p>
            )}
            {normalizeMutation.isError && (
              <p className="mb-3 text-sm text-red-600">
                {errorDetail(normalizeMutation.error, 'Terminology normalization failed.')}
              </p>
            )}
            {graphQuery.isLoading && <p className="text-sm text-slate-500">Loading claim graph...</p>}
            {graphQuery.data && (
              <ClaimGraphView
                encounterId={encounterId!}
                claims={graphQuery.data.claims}
                edges={graphQuery.data.edges}
              />
            )}
          </div>
        )}

        {activeTab === 'Clarifications' && <ClarificationQueue encounterId={encounterId!} />}

        {activeTab === 'Audit & Lineage' && (
          <div className="space-y-8">
            <AttestationTrail encounterId={encounterId!} />
            <div className="border-t border-slate-200 pt-6">
              <PipelineTraceView encounterId={encounterId!} />
            </div>
          </div>
        )}

        {activeTab === 'SOAP Note' && <SoapNoteView encounterId={encounterId!} />}
      </div>
    </div>
  )
}
