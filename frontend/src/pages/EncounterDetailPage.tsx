import { Link, useParams } from 'react-router-dom'

const TABS = ['Transcript', 'Claim Graph', 'SOAP Note', 'Clarifications', 'Audit & Lineage']

export default function EncounterDetailPage() {
  const { encounterId } = useParams()

  return (
    <div className="mx-auto max-w-5xl p-8">
      <Link to="/" className="text-sm text-indigo-600 hover:underline">
        ← Back to encounters
      </Link>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900">
        Encounter {encounterId}
      </h1>

      <div className="mt-6 flex gap-2 border-b border-slate-200">
        {TABS.map((tab, i) => (
          <div
            key={tab}
            className={`px-3 py-2 text-sm ${
              i === 0
                ? 'border-b-2 border-indigo-600 font-medium text-indigo-600'
                : 'text-slate-400'
            }`}
          >
            {tab}
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        This view will show speaker-labeled transcript segments, the claim
        graph, the SOAP note editor, the clarification queue, and the audit
        lineage view as later phases land.
      </div>
    </div>
  )
}
