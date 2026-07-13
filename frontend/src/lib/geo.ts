import type { DistrictBoundary } from '../types'

export interface Pt {
  lat: number
  lon: number
}

/** Initial compass bearing (degrees, 0 = north) from point a to b. */
export function bearing(a: Pt, b: Pt): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const toDeg = (r: number) => (r * 180) / Math.PI
  const φ1 = toRad(a.lat)
  const φ2 = toRad(b.lat)
  const Δλ = toRad(b.lon - a.lon)
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x =
    Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

/** Ray-casting point-in-ring test. `ring` is GeoJSON [lon, lat] pairs. */
function inRing(lat: number, lon: number, ring: number[][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const intersect =
      yi > lat !== yj > lat &&
      lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

/** Name of the raion whose polygon contains (lat, lon), or null. */
export function districtAt(
  lat: number,
  lon: number,
  boundaries: DistrictBoundary[],
): string | null {
  for (const b of boundaries) {
    const polys =
      b.geojson.type === 'Polygon'
        ? [b.geojson.coordinates]
        : b.geojson.coordinates
    for (const rings of polys) {
      // First ring is the outer boundary; ignore holes for this coarse check.
      if (inRing(lat, lon, rings[0] as number[][])) return b.name_uk
    }
  }
  return null
}
