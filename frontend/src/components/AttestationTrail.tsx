import { useQuery } from '@tanstack/react-query'
import { listAttestations, listEhrSubmissions } from '../api/encounters'
import type { AttestationAction } from '../types/domain'

const ACTION_LABELS: Record<AttestationAction, string> = {
  accepted: 'accepted',
  edited: 'edited',
  rejected: 'rejected',
  added: 'added',
  signed: 'signed the note',
}

const ACTION_STYLES: Record<AttestationAction, string> = {
  accepted: 'bg-emerald-100 text-emerald-800',
  edited: 'bg-indigo-100 text-indigo-800',
  rejected: 'bg-red-100 text-red-800',
  added: 'bg-slate-100 text-slate-700',
  signed: 'bg-slate-900 text-white',
}

export default function AttestationTrail({ encounterId }: { encounterId: string }) {
  const attestationsQuery = useQuery({
    queryKey: ['attestations', encounterId],
    queryFn: () => listAttestations(encounterId),
  })
  const submissionsQuery = useQuery({
    queryKey: ['ehr-submissions', encounterId],
    queryFn: () => listEhrSubmissions(encounterId),
  })

  return (
    <div>
      <p className="mb-4 text-sm text-slate-500">
        The clinician-facing half of the audit trail: every accept, edit, reject, and sign action, plus every
        handoff to the mock EHR. Sits alongside the LangGraph pipeline trace below -- that is the machine steps,
        this is the human decisions.
      </p>

      {attestationsQuery.isLoading && <p className="text-sm text-slate-500">Loading attestation trail...</p>}
      {attestationsQuery.data && attestationsQuery.data.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-300 p-6 text-center text-slate-500">
          No clinician actions recorded yet for this encounter.
        </div>
      )}
      {attestationsQuery.data && attestationsQuery.data.length > 0 && (
        <ol className="space-y-2">
          {attestationsQuery.data.map((a) => (
            <li key={a.id} className="rounded-md border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${ACTION_STYLES[a.action]}`}>
                  {ACTION_LABELS[a.action]}
                </span>
                <span className="text-xs text-slate-400">{new Date(a.created_at).toLocaleString()}</span>
              </div>
              {a.action === 'edited' && a.before_value && a.after_value && (
                <p className="mt-2 text-xs text-slate-600">
                  <span className="text-slate-400">before:</span> {a.before_value}
                  <br />
                  <span className="text-slate-400">after:</span> {a.after_value}
                </p>
              )}
              {a.action === 'rejected' && a.before_value && (
                <p className="mt-2 text-xs text-slate-600">{a.before_value}</p>
              )}
              {a.action === 'signed' && a.after_value && (
                <p className="mt-2 text-xs text-slate-600">{a.after_value}</p>
              )}
            </li>
          ))}
        </ol>
      )}

      {submissionsQuery.data && submissionsQuery.data.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-slate-700">
            Mock EHR submissions ({submissionsQuery.data.length})
          </h3>
          <div className="mt-2 space-y-2">
            {submissionsQuery.data.map((s) => (
              <div key={s.id} className="rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-600">
                Received {new Date(s.received_at).toLocaleString()} -- FHIR Bundle with{' '}
                {Array.isArray(s.bundle.entry) ? s.bundle.entry.length : 0} resources
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
