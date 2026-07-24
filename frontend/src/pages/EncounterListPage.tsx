import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createEncounter, listEncounters } from '../api/encounters'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export default function EncounterListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: encounters, isLoading, isError } = useQuery({
    queryKey: ['encounters'],
    queryFn: listEncounters,
  })

  const createMutation = useMutation({
    mutationFn: createEncounter,
    onSuccess: (encounter) => {
      queryClient.invalidateQueries({ queryKey: ['encounters'] })
      navigate(`/encounters/${encounter.id}`)
    },
  })

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Encounters</h1>
          <p className="mt-1 text-sm text-slate-500">
            Speaker-aware clinical evidence graph &amp; SOAP note system.
          </p>
        </div>
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {createMutation.isPending ? 'Creating...' : 'New encounter'}
        </button>
      </div>

      {isLoading && <p className="mt-6 text-sm text-slate-500">Loading encounters...</p>}
      {isError && (
        <p className="mt-6 text-sm text-red-600">
          Could not reach the API. Is the backend running on :8000?
        </p>
      )}

      {encounters && encounters.length === 0 && (
        <div className="mt-8 rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No encounters yet. Create one to ingest a transcript and extract claims.
        </div>
      )}

      {encounters && encounters.length > 0 && (
        <ul className="mt-6 divide-y divide-slate-200 rounded-md border border-slate-200 bg-white">
          {encounters.map((encounter) => (
            <li key={encounter.id}>
              <button
                type="button"
                onClick={() => navigate(`/encounters/${encounter.id}`)}
                className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
              >
                <span className="text-sm font-medium text-slate-900">
                  Encounter {encounter.id.slice(0, 8)}
                </span>
                <span className="text-xs text-slate-500">
                  {encounter.status} · {formatDate(encounter.started_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
