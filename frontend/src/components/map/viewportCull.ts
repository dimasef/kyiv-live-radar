import type { Threat, ThreatEvent } from '@/types'

/** A lat/lon rectangle, in the order Leaflet reports its own bounds. */
export interface LatLonBox {
  south: number
  west: number
  north: number
  east: number
}

/** The bounding box of a track's located sightings, or null when it has none.
 *
 * Reads `events` directly instead of going through `trackPoints()`: this runs
 * for every OPEN track every time the map settles, and all it needs are the
 * four extremes — not an allocated, de-duplicated list of points.
 */
export function trackBox(threat: Threat): LatLonBox | null {
  let south = Infinity
  let west = Infinity
  let north = -Infinity
  let east = -Infinity
  for (const ev of threat.events as ThreatEvent[]) {
    if (ev.lat == null || ev.lon == null) continue
    if (ev.lat < south) south = ev.lat
    if (ev.lat > north) north = ev.lat
    if (ev.lon < west) west = ev.lon
    if (ev.lon > east) east = ev.lon
  }
  return Number.isFinite(south) ? { south, west, north, east } : null
}

/** Should this track be handed to the map at all, given what is on screen?
 *
 * BOX OVERLAP, not "is one of its sightings inside the view". A long track can
 * have both ends off-screen while its line crosses the middle of the viewport,
 * and culling that would erase a vector the operator is looking straight at.
 * The box is a cheap over-approximation of the track's real shape, and
 * over-including is the safe direction: the cost of keeping one track too many
 * is a few DOM nodes, the cost of dropping one is a target that vanished.
 *
 * A city-wide track has no place on the map (it is a banner) and a track with
 * no located sighting has nothing to draw — both are dropped here so they never
 * count against the motion budget either.
 */
export function isVisible(threat: Threat, view: LatLonBox): boolean {
  if (threat.scope === 'city') return false
  const box = trackBox(threat)
  if (!box) return false
  return (
    box.south <= view.north &&
    box.north >= view.south &&
    box.west <= view.east &&
    box.east >= view.west
  )
}
