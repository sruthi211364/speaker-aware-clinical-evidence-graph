import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { extractClaims, listClaims, listTranscript } from '../api/encounters'
import ClaimList from '../components/ClaimList'
import TranscriptView from '../components/TranscriptView'

const TABS = ['Transcript', 'Claim Graph', 'SOAP Note', 'Clarifications', 'Audit & Lineage'] as const
type Tab = (typeof TABS)[number]

export default function EncounterDetailPage() {
  const { encounterId } = useParams<{ encounterId: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('Transcript')
  const queryClient = useQueryClient()

  const transcriptQuery = useQuery({
    queryKey: ['transcript', encounterId],
    queryFn: () => listTranscript(encounterId!),
    enabled: !!encounterId,
  })

  const claimsQuery = useQuery({
    queryKey: ['claims', encounterId],
    queryFn: () => listClaims(encounterId!),
    enabled: !!encounterId,
  })

  const extractMutation = useMutation({
    mutationFn: () => extractClaims(encounterId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claims', encounterId] })
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
            {transcriptQuery.isLoading && <p className="text-sm text-slate-500">Loading transcript...</p>}
            {transcriptQuery.data && <TranscriptView segments={transcriptQuery.data} />}
          </>
        )}

        {activeTab === 'Claim Graph' && (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Claim relationships (supports/contradicts/refines) arrive in Phase 3. For now: the flat
                extracted claim list.
              </p>
              <button
                type="button"
                onClick={() => extractMutation.mutate()}
                disabled={extractMutation.isPending}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {extractMutation.isPending ? 'Extracting...' : 'Extract claims'}
              </button>
            </div>
            {extractMutation.isError && (
              <p className="mb-3 text-sm text-red-600">
                {(extractMutation.error as { response?: { data?: { detail?: string } } })?.response?.data
                  ?.detail ?? 'Extraction failed.'}
              </p>
            )}
            {claimsQuery.isLoading && <p className="text-sm text-slate-500">Loading claims...</p>}
            {claimsQuery.data && <ClaimList claims={claimsQuery.data} />}
          </div>
        )}

        {activeTab !== 'Transcript' && activeTab !== 'Claim Graph' && (
          <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
            {activeTab} arrives in a later phase.
          </div>
        )}
      </div>
    </div>
  )
}
