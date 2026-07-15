import type { RawEventLink } from '@/types'

/** `events`/`noticeId` set = an authoritative match against real
 * ThreatEvent(s)/a Notice (this message became a feed card — one T/M chip
 * per event, since one message can close several tracks at once).
 * Otherwise `outcome` is a best-effort guess at why it didn't — see backend
 * api/raw_diagnosis.py. */
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
      {events.map((e) => (
        <span key={e.event_id} className="ml-1 opacity-70">
          T{e.threat_id}/M{e.event_id}
        </span>
      ))}
      {noticeId != null && <span className="ml-1 opacity-70">N{noticeId}</span>}
    </span>
  )
}
