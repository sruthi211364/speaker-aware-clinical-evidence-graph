import type { Claim, SourceType } from '../types/domain'

const SOURCE_LABELS: Record<SourceType, string> = {
  patient_speech: 'Patient speech',
  caregiver_report: 'Caregiver report',
  clinician_observation: 'Clinician observation',
  ehr_data: 'EHR data',
  device_data: 'Device data',
  clinician_judgment: 'Clinician judgment',
}

const STATUS_STYLES: Record<string, string> = {
  proposed: 'bg-slate-100 text-slate-700',
  supported: 'bg-emerald-100 text-emerald-800',
  contradicted: 'bg-red-100 text-red-800',
  ambiguous: 'bg-amber-100 text-amber-800',
  missing_context: 'bg-amber-100 text-amber-800',
  unsupported: 'bg-red-100 text-red-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  edited: 'bg-blue-100 text-blue-800',
  rejected: 'bg-slate-200 text-slate-500 line-through',
}

export default function ClaimList({ claims }: { claims: Claim[] }) {
  if (claims.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No claims extracted yet. Ingest a transcript, then run extraction.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {claims.map((claim) => (
        <div key={claim.id} className="rounded-md border border-slate-200 bg-white px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded bg-indigo-100 px-2 py-0.5 font-medium text-indigo-800">
              {claim.claim_type}
            </span>
            <span className="text-slate-400">from</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">
              {SOURCE_LABELS[claim.source_type]}
            </span>
            <span className={`ml-auto rounded px-2 py-0.5 font-medium ${STATUS_STYLES[claim.status] ?? ''}`}>
              {claim.status}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-900">{claim.text}</p>
          <p className="mt-1 text-xs text-slate-400">
            confidence {(claim.confidence * 100).toFixed(0)}%
          </p>
        </div>
      ))}
    </div>
  )
}
