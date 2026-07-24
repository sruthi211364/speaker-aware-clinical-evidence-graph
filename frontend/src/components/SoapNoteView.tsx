import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  acceptNoteLine,
  amendSoapNote,
  compileSoapNote,
  editNoteLine,
  exportNoteToFhir,
  getEncounter,
  getLatestSoapNote,
  getPipelineStatus,
  listAttestations,
  listClaims,
  listEhrSubmissions,
  rejectNoteLine,
  resumePipelineReview,
  signSoapNote,
} from '../api/encounters'
import type { SoapNoteLine, SoapSection } from '../types/domain'

const SECTION_LABELS: Record<SoapSection, string> = {
  subjective: 'Subjective',
  objective: 'Objective',
  assessment: 'Assessment',
  plan: 'Plan',
}

const SECTION_ORDER: SoapSection[] = ['subjective', 'objective', 'assessment', 'plan']

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

function NoteLineRow({
  line,
  claimTextById,
  isSigned,
  onAccept,
  onEdit,
  onReject,
}: {
  line: SoapNoteLine
  claimTextById: Map<string, string>
  isSigned: boolean
  onAccept: () => void
  onEdit: (text: string) => void
  onReject: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(line.text)

  const sourceLabel = line.claim_ids
    .map((id) => claimTextById.get(id))
    .filter((text): text is string => !!text)
    .map((text) => (text.length > 50 ? `${text.slice(0, 50)}...` : text))
    .join('  |  ')

  return (
    <div
      className={`rounded-md border p-3 ${
        line.is_rejected
          ? 'border-slate-200 bg-slate-50'
          : line.is_conflict
            ? 'border-red-300 bg-red-50'
            : 'border-slate-200 bg-white'
      }`}
    >
      {editing ? (
        <div className="space-y-2">
          <textarea
            className="w-full rounded border border-slate-300 p-2 text-sm"
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                onEdit(draft)
                setEditing(false)
              }}
              className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(line.text)
                setEditing(false)
              }}
              className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <p className={`text-sm text-slate-900 ${line.is_rejected ? 'text-slate-400 line-through' : ''}`}>
            {line.is_conflict && (
              <span className="mr-2 rounded bg-red-600 px-1.5 py-0.5 text-xs font-medium text-white">conflict</span>
            )}
            {line.is_rejected && (
              <span className="mr-2 rounded bg-slate-300 px-1.5 py-0.5 text-xs font-medium text-slate-700">
                rejected
              </span>
            )}
            {line.text}
          </p>
          {sourceLabel && <p className="mt-1 text-xs text-slate-400">Source: {sourceLabel}</p>}
          {!isSigned && !line.is_rejected && (
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={onAccept}
                className="rounded border border-emerald-300 px-2 py-0.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
              >
                Accept
              </button>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded border border-indigo-300 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={onReject}
                className="rounded border border-red-300 px-2 py-0.5 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Reject
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function SoapNoteView({ encounterId }: { encounterId: string }) {
  const queryClient = useQueryClient()

  const noteQuery = useQuery({
    queryKey: ['soap-note', encounterId],
    queryFn: () => getLatestSoapNote(encounterId),
    retry: false,
  })
  const claimsQuery = useQuery({
    queryKey: ['claims', encounterId],
    queryFn: () => listClaims(encounterId),
  })
  const statusQuery = useQuery({
    queryKey: ['pipeline-status', encounterId],
    queryFn: () => getPipelineStatus(encounterId),
  })
  const attestationsQuery = useQuery({
    queryKey: ['attestations', encounterId],
    queryFn: () => listAttestations(encounterId),
  })
  const encounterQuery = useQuery({
    queryKey: ['encounter', encounterId],
    queryFn: () => getEncounter(encounterId),
  })
  const submissionsQuery = useQuery({
    queryKey: ['ehr-submissions', encounterId],
    queryFn: () => listEhrSubmissions(encounterId),
  })

  const invalidateNote = () => {
    queryClient.invalidateQueries({ queryKey: ['soap-note', encounterId] })
    queryClient.invalidateQueries({ queryKey: ['attestations', encounterId] })
    queryClient.invalidateQueries({ queryKey: ['encounter', encounterId] })
  }

  const compileMutation = useMutation({
    mutationFn: () => compileSoapNote(encounterId),
    onSuccess: invalidateNote,
  })
  const resumeMutation = useMutation({
    mutationFn: () => resumePipelineReview(encounterId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-status', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['encounter', encounterId] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-trace', encounterId] })
    },
  })
  const lineActionMutation = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: invalidateNote,
  })
  const signMutation = useMutation({
    mutationFn: (noteId: string) => signSoapNote(encounterId, noteId),
    onSuccess: invalidateNote,
  })
  const amendMutation = useMutation({
    mutationFn: () => amendSoapNote(encounterId),
    onSuccess: invalidateNote,
  })
  const exportMutation = useMutation({
    mutationFn: (noteId: string) => exportNoteToFhir(encounterId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ehr-submissions', encounterId] })
    },
  })

  const claimTextById = new Map((claimsQuery.data ?? []).map((c) => [c.id, c.text]))

  if (noteQuery.isLoading || claimsQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading SOAP note...</p>
  }

  if (noteQuery.isError) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        <p className="mb-4">
          No SOAP note compiled yet. Either compile directly from the current claims, or run the full pipeline
          from the Audit &amp; Lineage tab (which also pauses here for review via a LangGraph interrupt).
        </p>
        <button
          type="button"
          onClick={() => compileMutation.mutate()}
          disabled={compileMutation.isPending}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {compileMutation.isPending ? 'Compiling...' : 'Compile SOAP note'}
        </button>
        {compileMutation.isError && (
          <p className="mt-3 text-sm text-red-600">{errorDetail(compileMutation.error, 'Compilation failed.')}</p>
        )}
      </div>
    )
  }

  const note = noteQuery.data!
  const isSigned = note.status === 'signed'
  const awaitingReview = statusQuery.data?.awaiting_review ?? false

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-md border border-slate-200 bg-white p-3">
        <div>
          <p className="text-sm font-medium text-slate-900">
            Note version {note.version} -- <span className="text-xs uppercase text-slate-500">{note.status}</span>
            {encounterQuery.data && (
              <span className="ml-2 text-xs uppercase text-slate-400">
                (encounter: {encounterQuery.data.status})
              </span>
            )}
          </p>
          <p className="text-xs text-slate-500">
            {awaitingReview
              ? 'The pipeline is paused at the clinician review step (a genuine LangGraph interrupt). Act on lines below, then resume.'
              : 'No pipeline run is currently paused for review on this encounter.'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => resumeMutation.mutate()}
          disabled={!awaitingReview || resumeMutation.isPending}
          className="shrink-0 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {resumeMutation.isPending ? 'Resuming...' : 'Finish review & resume pipeline'}
        </button>
      </div>
      {resumeMutation.isError && (
        <p className="text-sm text-red-600">{errorDetail(resumeMutation.error, 'Resume failed.')}</p>
      )}

      <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white p-3">
        {!isSigned && (
          <button
            type="button"
            onClick={() => signMutation.mutate(note.id)}
            disabled={signMutation.isPending}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {signMutation.isPending ? 'Signing...' : 'Sign note'}
          </button>
        )}
        {isSigned && (
          <>
            <button
              type="button"
              onClick={() => amendMutation.mutate()}
              disabled={amendMutation.isPending}
              className="rounded-md border border-indigo-300 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
            >
              {amendMutation.isPending ? 'Starting...' : 'Start new version (amend)'}
            </button>
            <button
              type="button"
              onClick={() => exportMutation.mutate(note.id)}
              disabled={exportMutation.isPending}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {exportMutation.isPending ? 'Exporting...' : 'Export to EHR (FHIR)'}
            </button>
          </>
        )}
        {submissionsQuery.data && submissionsQuery.data.length > 0 && (
          <span className="text-xs text-slate-500">
            Exported to the mock EHR {submissionsQuery.data.length} time
            {submissionsQuery.data.length === 1 ? '' : 's'}; last at{' '}
            {new Date(submissionsQuery.data[submissionsQuery.data.length - 1].received_at).toLocaleString()}
          </span>
        )}
      </div>
      {signMutation.isError && (
        <p className="text-sm text-red-600">{errorDetail(signMutation.error, 'Signing failed.')}</p>
      )}
      {amendMutation.isError && (
        <p className="text-sm text-red-600">{errorDetail(amendMutation.error, 'Starting a new version failed.')}</p>
      )}
      {exportMutation.isError && (
        <p className="text-sm text-red-600">{errorDetail(exportMutation.error, 'FHIR export failed.')}</p>
      )}

      {note.lines.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No claims have survived the policy engine to reach this note yet.
        </div>
      )}

      {SECTION_ORDER.map((section) => {
        const lines = note.lines.filter((l) => l.section === section)
        if (lines.length === 0) return null
        return (
          <div key={section}>
            <h3 className="text-sm font-semibold text-slate-700">{SECTION_LABELS[section]}</h3>
            <div className="mt-2 space-y-2">
              {lines.map((line) => (
                <NoteLineRow
                  key={line.id}
                  line={line}
                  claimTextById={claimTextById}
                  isSigned={isSigned}
                  onAccept={() => lineActionMutation.mutate(() => acceptNoteLine(encounterId, note.id, line.id))}
                  onEdit={(text) =>
                    lineActionMutation.mutate(() => editNoteLine(encounterId, note.id, line.id, text))
                  }
                  onReject={() => lineActionMutation.mutate(() => rejectNoteLine(encounterId, note.id, line.id))}
                />
              ))}
            </div>
          </div>
        )
      })}
      {lineActionMutation.isError && (
        <p className="text-sm text-red-600">{errorDetail(lineActionMutation.error, 'Action failed.')}</p>
      )}

      {attestationsQuery.data && attestationsQuery.data.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700">
            Review actions ({attestationsQuery.data.length})
          </h3>
          <div className="mt-2 space-y-1">
            {attestationsQuery.data.map((a) => (
              <p key={a.id} className="text-xs text-slate-500">
                <span className="font-medium text-slate-700">{a.action}</span>{' '}
                {new Date(a.created_at).toLocaleString()}
                {a.action === 'edited' && a.before_value && a.after_value && (
                  <>
                    {' '}
                    -- "{a.before_value.slice(0, 40)}" to "{a.after_value.slice(0, 40)}"
                  </>
                )}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
