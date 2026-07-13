import { bearing, type Pt } from '../../lib/geo'
import type { Threat, ThreatEvent } from '../../types'

/** Ordered, de-duplicated track points for a threat (consecutive repeats dropped). */
export function trackPoints(threat: Threat): Pt[] {
  const pts: Pt[] = []
  for (const ev of threat.events as ThreatEvent[]) {
    if (ev.lat == null || ev.lon == null) continue
    const last = pts[pts.length - 1]
    if (last && last.lat === ev.lat && last.lon === ev.lon) continue
    pts.push({ lat: ev.lat, lon: ev.lon })
  }
  return pts
}

/** A track "moves" only if its located sightings span ≥2 DISTINCT timestamps.
 * A single message naming several districts ("по Дарницькому та Соломʼянському")
 * produces several same-time events — an enumeration, not a trajectory — and
 * must not draw a connecting vector between those places. */
export function hasMovement(threat: Threat): boolean {
  const times = new Set<string>()
  for (const ev of threat.events as ThreatEvent[]) {
    if (ev.lat == null || ev.lon == null) continue
    times.add(ev.event_time)
    if (times.size >= 2) return true
  }
  return false
}

/** Bearing of the last leg of a track, or null if fewer than two points. */
export function headingOf(threat: Threat): number | null {
  const pts = trackPoints(threat)
  if (pts.length < 2) return null
  return bearing(pts[pts.length - 2], pts[pts.length - 1])
}
