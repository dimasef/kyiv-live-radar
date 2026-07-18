import { hasMovement, trackPoints } from '@/components/map/track'
import { angdiff, bearing, haversineKm, offsetKm, raionIdAt, type Pt } from '@/lib/geo'
import type { Home } from '@/store/homeSlice'
import type { DistrictBoundary, Threat } from '@/types'

/** Client twin of backend app/domain/home_danger.py — the server runs the SAME
 * rules per push subscription while this drives the instant map indication.
 * Change the two together (including these threshold defaults, which mirror
 * the backend Settings home_danger_* fields). */
export const HOME_DANGER = {
  bufferKm: 2,
  passSlackKm: 3,
  projectionKm: 20,
  angleTolDeg: 20,
  raionOverlapMin: 0.1,
} as const

/** Disc sample for zone->raion resolution — MUST stay identical to the backend
 * ZONE_SAMPLE (center + inner ring + edge ring, [radiusFraction, bearingDeg]). */
const ZONE_SAMPLE: Array<[number, number]> = [
  [0, 0],
  ...Array.from({ length: 8 }, (_, i) => [0.5, i * 45] as [number, number]),
  ...Array.from({ length: 16 }, (_, i) => [1, i * 22.5] as [number, number]),
]

/** Ids of every raion the home circle meaningfully overlaps (a zone on a
 * boundary sits in 2-3 raions) — mirror of backend raion_ids_for_zone. */
export function raionIdsForZone(home: Home, boundaries: DistrictBoundary[]): number[] {
  const hits = new Map<number, number>()
  for (const [frac, brg] of ZONE_SAMPLE) {
    const km = frac * home.radiusKm
    const rad = (brg * Math.PI) / 180
    const p = offsetKm(home, km * Math.cos(rad), km * Math.sin(rad))
    const id = raionIdAt(p.lat, p.lon, boundaries)
    if (id != null) hits.set(id, (hits.get(id) ?? 0) + 1)
  }
  const minHits = HOME_DANGER.raionOverlapMin * ZONE_SAMPLE.length
  return [...hits.entries()].filter(([, n]) => n >= minHits).map(([id]) => id)
}

export type HomeDangerLevel = 'none' | 'warning' | 'danger'

const LEVEL_RANK: Record<HomeDangerLevel, number> = { none: 0, warning: 1, danger: 2 }

/** Does the forward ray of the track's last leg pass the home zone? Home must
 * be in front, within the projection horizon, and either within cross-track
 * distance (exact) or angular tolerance (centroid headings lie by 15-20°). */
function vectorThreatens(pts: Pt[], home: Home): boolean {
  if (pts.length < 2) return false
  const prev = pts[pts.length - 2]
  const head = pts[pts.length - 1]
  const d = haversineKm(head, home)
  if (d > HOME_DANGER.projectionKm) return false
  const delta = Math.abs(angdiff(bearing(prev, head), bearing(head, home)))
  if (delta >= 90) return false
  const crossTrack = d * Math.sin((delta * Math.PI) / 180)
  return (
    crossTrack <= home.radiusKm + HOME_DANGER.passSlackKm ||
    delta <= HOME_DANGER.angleTolDeg
  )
}

export function threatDanger(
  threat: Threat,
  home: Home,
  homeRaionIds: number[],
): HomeDangerLevel {
  if (threat.scope === 'city') return 'none'
  const located = threat.events.filter((ev) => ev.lat != null && ev.lon != null)
  if (located.length === 0) return 'none'
  const dangerRadius = home.radiusKm + HOME_DANGER.bufferKm
  // Proximity is about where the target is NOW: only the latest sighting
  // cluster counts (same-time events can enumerate several districts), so a
  // track that passed the home area and moved on stops being danger.
  const latest = located.reduce((max, ev) => (ev.event_time > max ? ev.event_time : max), '')
  for (const ev of located) {
    if (ev.event_time !== latest) continue
    if (haversineKm({ lat: ev.lat!, lon: ev.lon! }, home) <= dangerRadius) return 'danger'
  }
  // Ballistic on a home raion: ANY event counts — sub-minute flight means a
  // raion callout is the strike itself, not a passing position.
  if (threat.target_type === 'ballistic' && homeRaionIds.length > 0) {
    if (located.some((ev) => homeRaionIds.includes(ev.district_id))) return 'danger'
  }
  if (hasMovement(threat) && vectorThreatens(trackPoints(threat), home)) return 'warning'
  return 'none'
}

/** Max danger over all OPEN district tracks — impacts and closed tracks are
 * history, not an approaching target. */
export function homeDanger(
  threats: Record<number, Threat>,
  home: Home,
  boundaries: DistrictBoundary[],
): HomeDangerLevel {
  const homeRaionIds = raionIdsForZone(home, boundaries)
  let worst: HomeDangerLevel = 'none'
  for (const threat of Object.values(threats)) {
    if (threat.closed_at != null || threat.kind === 'impact') continue
    const level = threatDanger(threat, home, homeRaionIds)
    if (LEVEL_RANK[level] > LEVEL_RANK[worst]) worst = level
    if (worst === 'danger') break
  }
  return worst
}
