import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPipelineTrace, runPipeline } from '../api/encounters'

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

export default function PipelineTraceView({ encounterId }: { encounterId: string }) {
  const queryClient = useQueryClient()

  const traceQuery = useQuery({
    queryKey: ['pipeline-trace', encounterId],
    queryFn: () => getPipelineTrace(encounterId),
  })

  const runMutation = useMutation({
    mutationFn: () => runPipeline(encounterId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-trace', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['clarifications', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['soap-note', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-status', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['encounter', encounterId] })
    },
  })

  const steps = traceQuery.data?.filter((entry) => entry.node !== null) ?? []

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-slate-500">
          LangGraph run trace: the technical node-by-node history behind this encounter's pipeline,
          checkpointed to Postgres. The full audit and lineage view (combined with the clinician
          attestation trail) arrives in a later phase.
        </p>
        <button
          type="button"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {runMutation.isPending ? 'Running...' : 'Run full pipeline'}
        </button>
      </div>

      {runMutation.isError && (
        <p className="mb-3 text-sm text-red-600">{errorDetail(runMutation.error, 'Pipeline run failed.')}</p>
      )}

      {traceQuery.isLoading && <p className="text-sm text-slate-500">Loading trace...</p>}

      {steps.length === 0 && !traceQuery.isLoading && (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No pipeline run yet for this encounter.
        </div>
      )}

      {steps.length > 0 && (
        <ol className="space-y-2">
          {steps.map((entry, i) => (
            <li key={i} className="rounded-md border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between text-xs">
                <span className="rounded bg-indigo-100 px-2 py-0.5 font-medium text-indigo-800">
                  {entry.node}
                </span>
                <span className="text-slate-400">step {entry.step}</span>
              </div>
              {entry.result && (
                <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                  {JSON.stringify(entry.result, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
