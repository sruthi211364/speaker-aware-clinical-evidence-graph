import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listPolicyVerdicts } from '../api/encounters'
import ClaimCitationsPanel from './ClaimCitationsPanel'
import type { Claim, ClaimEdge, PolicyVerdict, SourceType } from '../types/domain'

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

const STATUS_BADGES: Partial<Record<Claim['status'], { label: string; className: string }>> = {
  unsafe: { label: 'clinical safety flag', className: 'bg-red-600 text-white' },
  contradicted: { label: 'contradicted', className: 'bg-red-100 text-red-800' },
  unsupported: { label: 'unsupported', className: 'bg-slate-200 text-slate-600' },
  missing_context: { label: 'missing context', className: 'bg-amber-100 text-amber-800' },
  ambiguous: { label: 'temporally ambiguous', className: 'bg-amber-100 text-amber-800' },
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

export default function ClaimGraphView({
  encounterId,
  claims,
  edges,
}: {
  encounterId: string
  claims: Claim[]
  edges: ClaimEdge[]
}) {
  const [expandedClaimId, setExpandedClaimId] = useState<string | null>(null)
  const claimById = new Map(claims.map((c) => [c.id, c]))
  const contradictions = edges.filter((e) => e.relation === 'contradicts')
  const otherEdges = edges.filter((e) => e.relation !== 'contradicts')

  const verdictsQuery = useQuery({
    queryKey: ['policy-verdicts', encounterId],
    queryFn: () => listPolicyVerdicts(encounterId),
  })
  const verdictsByClaim = new Map<string, PolicyVerdict[]>()
  for (const v of verdictsQuery.data ?? []) {
    verdictsByClaim.set(v.claim_id, [...(verdictsByClaim.get(v.claim_id) ?? []), v])
  }

  const unsafeClaims = claims.filter((c) => c.status === 'unsafe')

  if (claims.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No claims yet. Extract claims first, then build the graph.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {unsafeClaims.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-800">
            ⚠ Clinical safety flags ({unsafeClaims.length})
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Grounded in retrieved drug interaction / allergy data -- review before this reaches a note.
          </p>
          <div className="mt-2 space-y-2">
            {unsafeClaims.map((claim) => {
              const rationale = verdictsByClaim
                .get(claim.id)
                ?.find((v) => v.check_type === 'clinical_safety' && !v.passed)?.rationale
              return (
                <div key={claim.id} className="rounded-md border-2 border-red-600 bg-red-50 p-3">
                  <p className="text-sm font-medium text-slate-900">{claim.text}</p>
                  {rationale && <p className="mt-1 text-xs text-red-800">{rationale}</p>}
                </div>
              )
            })}
          </div>
        </div>
      )}

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
            const badge = STATUS_BADGES[claim.status]
            const isExpanded = expandedClaimId === claim.id
            const failedRationales = (verdictsByClaim.get(claim.id) ?? [])
              .filter((v) => !v.passed && v.rationale)
              .map((v) => v.rationale)
            return (
              <div
                key={claim.id}
                className={`rounded-md border px-4 py-3 ${
                  claim.status === 'unsafe'
                    ? 'border-2 border-red-600 bg-red-50'
                    : badge
                      ? 'border-slate-300 bg-white'
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
                  {badge && (
                    <span className={`rounded px-2 py-0.5 font-medium ${badge.className}`}>{badge.label}</span>
                  )}
                  <button
                    type="button"
                    onClick={() => setExpandedClaimId(isExpanded ? null : claim.id)}
                    className="ml-auto text-xs font-medium text-indigo-600 hover:underline"
                  >
                    {isExpanded ? 'Hide citations' : 'Show citations'}
                  </button>
                </div>
                <p className="mt-2 text-sm text-slate-900">{claim.text}</p>
                {failedRationales.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
                    {failedRationales.map((r, i) => (
                      <li key={i}>- {r}</li>
                    ))}
                  </ul>
                )}
                {isExpanded && <ClaimCitationsPanel encounterId={encounterId} claimId={claim.id} />}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
