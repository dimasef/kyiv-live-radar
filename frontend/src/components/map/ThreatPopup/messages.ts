import type { ThreatEvent } from '@/types'

/** The messages that produced this track — one per distinct source message (an
 * event repeated per district shares a message_id), oldest first so the popup
 * reads as the target's story. */
export function dedupeMessages(events: ThreatEvent[]): ThreatEvent[] {
  const out: ThreatEvent[] = []
  const seen = new Set<number | string>()
  for (const ev of events) {
    const key = ev.source_message_id ?? ev.raw_text
    if (seen.has(key)) continue
    seen.add(key)
    out.push(ev)
  }
  return out
}
