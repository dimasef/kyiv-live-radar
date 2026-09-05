import type { Threat, ThreatEvent } from '@/types'

export interface SourceSplit {
  /** The channel whose sightings draw the path, when known. */
  lead: string | null
  /** How many sightings came from other channels, and their names. */
  echoCount: number
  echoSources: string[]
}

export function sourceSplit(threat: Threat): SourceSplit {
  const psid = threat.path_source_id
  const events = threat.events as ThreatEvent[]
  const lead = psid == null ? null : (events.find((ev) => ev.source_id === psid)?.source_name ?? null)
  const echo = psid == null ? [] : events.filter((ev) => ev.source_id !== psid && !ev.manual && ev.source_id != null)
  const echoSources = [...new Set(echo.map((ev) => ev.source_name).filter((n): n is string => !!n))]
  return { lead, echoCount: echo.length, echoSources }
}
