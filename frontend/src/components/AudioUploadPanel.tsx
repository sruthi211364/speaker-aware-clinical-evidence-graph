import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { commitAudioTranscript, previewAudioTranscript } from '../api/encounters'
import type { AudioTranscriptionPreview, SpeakerRole } from '../types/domain'

const SPEAKER_ROLE_OPTIONS: SpeakerRole[] = ['clinician', 'patient', 'caregiver', 'system']

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

export default function AudioUploadPanel({ encounterId }: { encounterId: string }) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<AudioTranscriptionPreview | null>(null)
  const [roleMap, setRoleMap] = useState<Record<string, SpeakerRole>>({})

  const previewMutation = useMutation({
    mutationFn: (f: File) => previewAudioTranscript(encounterId, f),
    onSuccess: (data) => {
      setPreview(data)
      setRoleMap(Object.fromEntries(data.speaker_labels.map((label) => [label, 'clinician' as SpeakerRole])))
    },
  })

  const commitMutation = useMutation({
    mutationFn: () => commitAudioTranscript(encounterId, preview!.utterances, roleMap),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', encounterId] })
      setPreview(null)
      setFile(null)
    },
  })

  return (
    <div className="mb-6 rounded-md border border-slate-200 bg-white p-4">
      <p className="text-sm font-medium text-slate-900">Upload raw audio</p>
      <p className="mt-1 text-xs text-slate-500">
        Transcribed and diarized via AssemblyAI. Diarization only tells us "Speaker A" vs "Speaker B" -- who's who
        has to be assigned by hand below before anything is saved.
      </p>

      {!preview && (
        <div className="mt-3 flex items-center gap-2">
          <input
            type="file"
            accept="audio/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-slate-600"
          />
          <button
            type="button"
            onClick={() => file && previewMutation.mutate(file)}
            disabled={!file || previewMutation.isPending}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {previewMutation.isPending ? 'Transcribing...' : 'Transcribe'}
          </button>
        </div>
      )}
      {previewMutation.isError && (
        <p className="mt-2 text-sm text-red-600">{errorDetail(previewMutation.error, 'Transcription failed.')}</p>
      )}

      {preview && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-4">
            {preview.speaker_labels.map((label) => (
              <label key={label} className="flex items-center gap-2 text-sm text-slate-700">
                Speaker {label} is:
                <select
                  value={roleMap[label] ?? 'clinician'}
                  onChange={(e) => setRoleMap((prev) => ({ ...prev, [label]: e.target.value as SpeakerRole }))}
                  className="rounded border border-slate-300 px-2 py-1 text-sm"
                >
                  {SPEAKER_ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          <div className="max-h-64 space-y-1 overflow-y-auto rounded border border-slate-100 bg-slate-50 p-2">
            {preview.utterances.map((u, i) => (
              <p key={i} className="text-xs text-slate-600">
                <span className="font-medium text-slate-800">Speaker {u.speaker_label}:</span> {u.text}
              </p>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => commitMutation.mutate()}
              disabled={commitMutation.isPending}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {commitMutation.isPending ? 'Saving...' : `Save ${preview.utterances.length} segments`}
            </button>
            <button
              type="button"
              onClick={() => {
                setPreview(null)
                setFile(null)
              }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              Discard
            </button>
          </div>
          {commitMutation.isError && (
            <p className="text-sm text-red-600">{errorDetail(commitMutation.error, 'Saving the transcript failed.')}</p>
          )}
        </div>
      )}
    </div>
  )
}
