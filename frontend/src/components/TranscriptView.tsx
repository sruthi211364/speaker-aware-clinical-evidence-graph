import type { SpeakerRole, TranscriptSegment } from '../types/domain'

const SPEAKER_STYLES: Record<SpeakerRole, string> = {
  patient: 'bg-blue-50 border-blue-200 text-blue-900',
  caregiver: 'bg-amber-50 border-amber-200 text-amber-900',
  clinician: 'bg-slate-100 border-slate-300 text-slate-900',
  system: 'bg-slate-50 border-slate-200 text-slate-500',
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export default function TranscriptView({ segments }: { segments: TranscriptSegment[] }) {
  if (segments.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
        No transcript yet for this encounter.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {segments.map((segment) => (
        <div
          key={segment.id}
          className={`rounded-md border px-4 py-3 ${SPEAKER_STYLES[segment.speaker_role]}`}
        >
          <div className="flex items-baseline justify-between text-xs font-medium uppercase tracking-wide opacity-70">
            <span>{segment.speaker_role}</span>
            <span>
              {formatTimestamp(segment.start_ms)} - {formatTimestamp(segment.end_ms)}
            </span>
          </div>
          <p className="mt-1 text-sm">{segment.text}</p>
        </div>
      ))}
    </div>
  )
}
