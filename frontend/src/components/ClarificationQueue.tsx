import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { answerClarification, listClarifications } from '../api/encounters'

export default function ClarificationQueue({ encounterId }: { encounterId: string }) {
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const { data, isLoading, isError } = useQuery({
    queryKey: ['clarifications', encounterId],
    queryFn: () => listClarifications(encounterId),
  })

  const answerMutation = useMutation({
    mutationFn: ({ clarificationId, answerText }: { clarificationId: string; answerText: string }) =>
      answerClarification(encounterId, clarificationId, answerText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clarifications', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['claim-graph', encounterId] })
    },
  })

  if (isLoading) return <p className="text-sm text-slate-500">Loading clarifications...</p>
  if (isError) return <p className="text-sm text-red-600">Failed to load clarifications.</p>
  if (!data || data.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No clarification questions. Run the policy check to generate any that are needed.
      </div>
    )
  }

  const open = data.filter((q) => !q.resolved)
  const resolved = data.filter((q) => q.resolved)

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-amber-700">Open questions ({open.length})</h3>
        <div className="mt-2 space-y-3">
          {open.map((q) => (
            <div key={q.id} className="rounded-md border border-amber-300 bg-amber-50 p-3">
              <p className="text-sm text-slate-900">{q.question_text}</p>
              <div className="mt-2 flex gap-2">
                <input
                  type="text"
                  value={drafts[q.id] ?? ''}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [q.id]: e.target.value }))}
                  placeholder="Clinician's answer..."
                  className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                />
                <button
                  type="button"
                  disabled={!drafts[q.id]?.trim() || answerMutation.isPending}
                  onClick={() => answerMutation.mutate({ clarificationId: q.id, answerText: drafts[q.id] })}
                  className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  Answer
                </button>
              </div>
            </div>
          ))}
          {open.length === 0 && <p className="text-sm text-slate-500">No open questions.</p>}
        </div>
      </div>

      {resolved.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700">Resolved ({resolved.length})</h3>
          <div className="mt-2 space-y-2">
            {resolved.map((q) => (
              <div key={q.id} className="rounded-md border border-slate-200 bg-white p-3 text-sm text-slate-500">
                {q.question_text}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
