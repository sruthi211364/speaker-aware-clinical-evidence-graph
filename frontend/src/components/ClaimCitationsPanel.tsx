import { useQuery } from '@tanstack/react-query'
import { getClaimCitations } from '../api/encounters'
import type { GroundingSourceType } from '../types/domain'

const SOURCE_TYPE_LABELS: Record<GroundingSourceType, string> = {
  guideline: 'Guideline',
  drug_data: 'Drug data',
  prior_encounter: 'Prior encounter',
  coded_vocabulary: 'Coded vocabulary',
}

export default function ClaimCitationsPanel({
  encounterId,
  claimId,
}: {
  encounterId: string
  claimId: string
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['claim-citations', encounterId, claimId],
    queryFn: () => getClaimCitations(encounterId, claimId),
  })

  if (isLoading) return <p className="mt-2 text-xs text-slate-500">Loading citations...</p>
  if (isError) return <p className="mt-2 text-xs text-red-600">Failed to load citations.</p>
  if (!data || data.length === 0) {
    return (
      <p className="mt-2 text-xs text-slate-500">
        No grounding citations yet. Run "Ground claims" to retrieve supporting evidence.
      </p>
    )
  }

  return (
    <div className="mt-2 space-y-2 border-t border-slate-200 pt-2">
      {data.map((citation) => (
        <div key={citation.id} className="rounded border border-slate-200 bg-slate-50 p-2">
          <div className="flex items-center justify-between text-xs">
            <span className="rounded bg-white px-1.5 py-0.5 font-medium text-slate-700">
              {SOURCE_TYPE_LABELS[citation.source_type]}
              {citation.source_identifier ? ` · ${citation.source_identifier}` : ''}
            </span>
            <span className="text-slate-400">relevance {(citation.relevance_score * 100).toFixed(0)}%</span>
          </div>
          {citation.excerpt && <p className="mt-1 text-xs text-slate-600">{citation.excerpt}</p>}
        </div>
      ))}
    </div>
  )
}
