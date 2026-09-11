import type { ThreatState } from './threatIcons'
import type { Threat } from './types'

/** Head-marker/glyph state derived from track status. `heading`/`directional`
 * only matter on the map (a directional type with no heading yet reads as a
 * plain fix, not a moving arrow) — the feed never passes them and always
 * collapses to 'active'. */
export function threatState(
  threat: Threat,
  opts: { heading?: number | null; directional?: boolean } = {},
): ThreatState {
  if (threat.status === 'impact') return 'impact'
  if (threat.status === 'destroyed' || threat.status === 'lost') return 'destroyed'
  if (opts.directional && opts.heading == null) return 'fix'
  return 'active'
}

/** Localized target-type label, suppressed for an impact with no confirmed
 * type — an "unknown" hit is aftermath (a strike whose weapon nobody
 * named), not worth labelling "unknown" next to the marker. */
export function typeLabel(threat: Threat, t: (key: string) => string): string | null {
  if (threat.status === 'impact' && threat.target_type === 'unknown') return null
  return t(`target.${threat.target_type}`)
}
