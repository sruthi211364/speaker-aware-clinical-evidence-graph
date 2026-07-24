import type { Claim, ClaimEdge, SourceType } from '../types/domain'

const SOURCE_LABELS: Record<SourceType, string> = {
  patient_speech: 'Patient',
  caregiver_report: 'Caregiver',
  clinician_observation: 'Clinician',
  ehr_data: 'EHR',
  device_data: 'Device',
  clinician_judgment: 'Clinician judgment',
}

const RELATION_LABELS: Record<string, string> = {
  supports: 'supports',
  contradicts: 'contradicts',
  refines: 'refines',
  duplicates: 'duplicates',
  depends_on_temporal_context: 'depends on temporal context of',
}

function ClaimChip({ claim }: { claim: Claim }) {
  return (
    <div className="flex-1 rounded-md border border-slate-200 bg-white p-3">
      <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
        {SOURCE_LABELS[claim.source_type]}
      </span>
      <p className="mt-2 text-sm text-slate-900">{claim.text}</p>
    </div>
  )
}

export default function ClaimGraphView({ claims, edges }: { claims: Claim[]; edges: ClaimEdge[] }) {
  const claimById = new Map(claims.map((c) => [c.id, c]))
  const contradictions = edges.filter((e) => e.relation === 'contradicts')
  const otherEdges = edges.filter((e) => e.relation !== 'contradicts')
  const contradictedClaimIds = new Set(contradictions.flatMap((e) => [e.source_claim_id, e.target_claim_id]))

  if (claims.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No claims yet. Extract claims first, then build the graph.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {contradictions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-700">
            Conflicting accounts ({contradictions.length})
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Kept visible side by side rather than merged into one statement.
          </p>
          <div className="mt-2 space-y-3">
            {contradictions.map((edge) => {
              const source = claimById.get(edge.source_claim_id)
              const target = claimById.get(edge.target_claim_id)
              if (!source || !target) return null
              return (
                <div key={edge.id} className="rounded-md border border-red-300 bg-red-50 p-3">
                  <div className="flex gap-3">
                    <ClaimChip claim={source} />
                    <span className="self-center text-red-500">⚡</span>
                    <ClaimChip claim={target} />
                  </div>
                  {edge.rationale && <p className="mt-2 text-xs text-red-700">{edge.rationale}</p>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {otherEdges.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Other relationships ({otherEdges.length})</h3>
          <div className="mt-2 space-y-2">
            {otherEdges.map((edge) => {
              const source = claimById.get(edge.source_claim_id)
              const target = claimById.get(edge.target_claim_id)
              if (!source || !target) return null
              return (
                <div key={edge.id} className="rounded-md border border-slate-200 bg-white p-3 text-sm">
                  <p className="text-slate-900">
                    <span className="font-medium">{source.text}</span>{' '}
                    <span className="text-indigo-600">{RELATION_LABELS[edge.relation]}</span>{' '}
                    <span className="font-medium">{target.text}</span>
                  </p>
                  {edge.rationale && <p className="mt-1 text-xs text-slate-500">{edge.rationale}</p>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-slate-700">All claims ({claims.length})</h3>
        <div className="mt-2 space-y-2">
          {claims.map((claim) => {
            const isContradicted = contradictedClaimIds.has(claim.id)
            const isUnsupported = claim.status === 'unsupported'
            return (
              <div
                key={claim.id}
                className={`rounded-md border px-4 py-3 ${
                  isContradicted
                    ? 'border-red-300 bg-red-50'
                    : isUnsupported
                      ? 'border-slate-300 bg-slate-100 opacity-70'
                      : 'border-slate-200 bg-white'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded bg-indigo-100 px-2 py-0.5 font-medium text-indigo-800">
                    {claim.claim_type}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">
                    {SOURCE_LABELS[claim.source_type]}
                  </span>
                  {isContradicted && (
                    <span className="rounded bg-red-100 px-2 py-0.5 font-medium text-red-800">
                      contradicted
                    </span>
                  )}
                  {isUnsupported && (
                    <span className="rounded bg-slate-200 px-2 py-0.5 font-medium text-slate-600">
                      unsupported
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-900">{claim.text}</p>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
