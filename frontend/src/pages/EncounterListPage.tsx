import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'

async function fetchHealth() {
  const res = await apiClient.get('/health')
  return res.data as { status: string }
}

export default function EncounterListPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: false,
  })

  return (
    <div className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold text-slate-900">Encounters</h1>
      <p className="mt-1 text-sm text-slate-500">
        Speaker-aware clinical evidence graph &amp; SOAP note system.
      </p>

      <div className="mt-4 rounded-md border border-slate-200 bg-white p-4 text-sm">
        <span className="font-medium">Backend status: </span>
        {isLoading && <span className="text-slate-500">checking…</span>}
        {isError && (
          <span className="text-red-600">
            unreachable (is the API running on :8000?)
          </span>
        )}
        {data && <span className="text-emerald-600">{data.status}</span>}
      </div>

      <div className="mt-8 rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No encounters yet. Encounter ingestion arrives in Phase 2.
      </div>

      <Link
        to="/encounters/demo"
        className="mt-4 inline-block text-sm text-indigo-600 hover:underline"
      >
        View placeholder encounter detail shell →
      </Link>
    </div>
  )
}
