import { hasMovement, pathEvents, trackPoints } from '@/components/map/track'
import { angdiff, bearing, haversineKm, offsetKm, raionIdAt, type Pt } from '@/lib/geo'
import type { Home } from '@/store/homeSlice'
import type { DistrictBoundary, Threat, ThreatEvent } from '@/types'

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

export interface ThreatDanger {
  level: HomeDangerLevel
  /** The sighting that triggered the level, mirroring the second value the
   * backend's assess() returns for the push body ("~4 км від дому
   * (Шевченківський)"). The map deliberately draws nothing for it: a lone ring
   * away from the track head read as an unexplained phantom, and the home
   * marker's own colour already says danger is near. Null for none. */
  triggerEventId: number | null
}

type Located = ThreatEvent & { lat: number; lon: number }

/** The sightings that say where the target IS: every source's newest cluster
 * while that source's fix is still valid (`position_valid_until`, set by the
 * backend from the same windows that retire the track). Without `nowMs`, or
 * for history that carries no validity, the track's newest cluster. Mirror of
 * backend current_position_events. */
export function currentPositionEvents(threat: Threat, nowMs?: number): Located[] {
  const located = (threat.events as ThreatEvent[]).filter(
    (ev): ev is Located => ev.lat != null && ev.lon != null,
  )
  if (located.length === 0) return []
  const dated = nowMs != null && located.every((ev) => ev.position_valid_until != null)
  if (!dated) {
    const latest = located.reduce((max, ev) => (ev.event_time > max ? ev.event_time : max), '')
    return located.filter((ev) => ev.event_time === latest)
  }
  const latestBySource = new Map<number | null | undefined, string>()
  for (const ev of located) {
    const cur = latestBySource.get(ev.source_id)
    if (cur == null || ev.event_time > cur) latestBySource.set(ev.source_id, ev.event_time)
  }
  return located.filter(
    (ev) =>
      ev.event_time === latestBySource.get(ev.source_id) &&
      Date.parse(ev.position_valid_until!) > nowMs,
  )
}

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
  nowMs?: number,
): ThreatDanger {
  const none: ThreatDanger = { level: 'none', triggerEventId: null }
  if (threat.scope === 'city') return none
  const located = threat.events.filter((ev) => ev.lat != null && ev.lon != null)
  if (located.length === 0) return none
  const dangerRadius = home.radiusKm + HOME_DANGER.bufferKm
  // Proximity is about where the target is NOW — the nearest still-valid fix.
  let nearest: ThreatEvent | null = null
  let nearestKm = Infinity
  for (const ev of currentPositionEvents(threat, nowMs)) {
    const km = haversineKm({ lat: ev.lat, lon: ev.lon }, home)
    if (km <= dangerRadius && km < nearestKm) {
      nearest = ev
      nearestKm = km
    }
  }
  if (nearest) return { level: 'danger', triggerEventId: nearest.id }
  // Ballistic on a home raion: ANY event counts — sub-minute flight means a
  // raion callout is the strike itself, not a passing position.
  if (threat.target_type === 'ballistic' && homeRaionIds.length > 0) {
    const hit = located.find((ev) => homeRaionIds.includes(ev.district_id))
    if (hit) return { level: 'danger', triggerEventId: hit.id }
  }
  if (hasMovement(threat) && vectorThreatens(trackPoints(threat), home)) {
    const path = pathEvents(threat)
    return { level: 'warning', triggerEventId: path[path.length - 1]?.id ?? null }
  }
  return none
}

/** Max danger over all OPEN district tracks — impacts and closed tracks are
 * history, not an approaching target.
 *
 * Takes the home raion ids rather than deriving them: they cost 25 point-in-
 * polygon tests across every raion boundary, depend only on the home zone, and
 * this runs on every live frame. Callers memoize them (see MapView). */
export interface HomeDangerState {
  worst: HomeDangerLevel
  byThreat: Record<number, ThreatDanger>
}

export const NO_DANGER: HomeDangerState = { worst: 'none', byThreat: {} }

export function homeDangerFor(
  threats: Record<number, Threat>,
  home: Home,
  homeRaionIds: number[],
  nowMs?: number,
): HomeDangerState {
  let worst: HomeDangerLevel = 'none'
  const byThreat: Record<number, ThreatDanger> = {}
  for (const threat of Object.values(threats)) {
    if (threat.closed_at != null || threat.kind === 'impact') continue
    const d = threatDanger(threat, home, homeRaionIds, nowMs)
    if (d.level === 'none') continue
    byThreat[threat.id] = d
    if (LEVEL_RANK[d.level] > LEVEL_RANK[worst]) worst = d.level
  }
  return { worst, byThreat }
}

/** `homeDangerFor` with the raion resolution done inline — for one-off callers
 * that have no place to cache it. */
export function homeDanger(
  threats: Record<number, Threat>,
  home: Home,
  boundaries: DistrictBoundary[],
  nowMs?: number,
): HomeDangerLevel {
  return homeDangerFor(threats, home, raionIdsForZone(home, boundaries), nowMs).worst
}
