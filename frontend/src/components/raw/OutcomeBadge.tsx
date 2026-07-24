import type { RawEventLink } from '@/types'

/** Compact outcome label for the row header: 'подія'/'нотіс' when an
 * authoritative ThreatEvent/Notice matched (with a ×N count when one message
 * closed several tracks at once), a best-effort diagnosis label otherwise (see
 * backend api/raw_diagnosis.py). The per-event T/M chips + their assigned type
 * live in a wrapping row below the text (RawMessageRow), so a message that
 * closed many tracks no longer overflows this header. */
export default function OutcomeBadge({
  outcome,
  events,
  noticeId,
}: {
  outcome: string
  events: RawEventLink[]
  noticeId: number | null
}) {
  const tone =
    events.length > 0
      ? 'bg-emerald-400/15 text-emerald-300'
      : noticeId != null
        ? 'bg-sky-400/15 text-sky-300'
        : 'bg-white/[0.06] text-slate-400'
  return (
    <span
      className={`whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone}`}
    >
      {outcome}
      {events.length > 1 && <span className="ml-1 opacity-70">×{events.length}</span>}
    </span>
  )
}
