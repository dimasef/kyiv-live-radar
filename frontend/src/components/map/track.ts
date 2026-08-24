import { bearing, type Pt } from '@/lib/geo'
import type { Threat, ThreatEvent } from '@/types'

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

/** A track "moves" if its located sightings span ≥2 DISTINCT timestamps, or if
 * the parser saw a path STATED in one message.
 *
 * The timestamp rule alone is what keeps an enumeration from drawing a vector:
 * "по Дарницькому та Соломʼянському" is several same-time events naming places
 * a drone is near, not a trajectory between them. But the northern spotter
 * channel writes movement as one message per leg — «Мамекине на Смяч» — which
 * is also same-time, and 39 real drone tracks drew as bare dots because of it.
 * Only the parser can tell the two apart (a path connective sits between the
 * two place names), so the backend decides and sends `movement_stated`. */
export function hasMovement(threat: Threat): boolean {
  if (threat.movement_stated && trackPoints(threat).length > 1) return true
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

/** Presumed heading for a drone sighted as a single point (no real vector yet):
 * it still flies INTO the city, so point the glyph toward `target` (Kyiv
 * centre) rather than a meaningless due-north. `seed` (the threat id) drives a
 * deterministic ±`spread`° north/south jitter — a fresh cluster shouldn't look
 * regimented all aiming at one pixel, and a deterministic value stays stable
 * across re-renders (no icon churn, unlike Math.random). */
export function inboundHeading(from: Pt, target: Pt, seed: number, spread = 20): number {
  const hash = Math.sin(seed * 12.9898) * 43758.5453
  const jitter = ((hash - Math.floor(hash)) * 2 - 1) * spread
  return (bearing(from, target) + jitter + 360) % 360
}
