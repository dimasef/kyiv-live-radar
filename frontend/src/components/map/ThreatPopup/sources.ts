import type { Threat, ThreatEvent } from '@/types'

/** A channel as the popup needs it: the id resolves its public Telegram link
 * against the store's source list, the name is what gets drawn. */
export interface SourceRef {
  id: number
  name: string
}

export interface SourceSplit {
  /** The channel whose sightings draw the path, when known. */
  lead: SourceRef | null
  /** How many sightings came from other channels, and those channels. */
  echoCount: number
  echoSources: SourceRef[]
}

export function sourceSplit(threat: Threat): SourceSplit {
  const psid = threat.path_source_id
  const events = threat.events as ThreatEvent[]
  const leadName = psid == null ? null : (events.find((ev) => ev.source_id === psid)?.source_name ?? null)
  const lead = psid != null && leadName != null ? { id: psid, name: leadName } : null
  const echo = psid == null ? [] : events.filter((ev) => ev.source_id !== psid && !ev.manual && ev.source_id != null)
  const seen = new Map<number, string>()
  for (const ev of echo) {
    if (ev.source_id != null && ev.source_name && !seen.has(ev.source_id)) {
      seen.set(ev.source_id, ev.source_name)
    }
  }
  const echoSources = [...seen].map(([id, name]) => ({ id, name }))
  return { lead, echoCount: echo.length, echoSources }
}
