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

/** Great-circle distance in km — same formula as backend geometry.haversine_km. */
export function haversineKm(a: Pt, b: Pt): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dφ = toRad(b.lat - a.lat)
  const dλ = toRad(b.lon - a.lon)
  const h =
    Math.sin(dφ / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dλ / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

/** Signed smallest difference a-b between two bearings, in (-180, 180]. */
export function angdiff(a: number, b: number): number {
  const d = (((a - b) % 360) + 360) % 360
  return d > 180 ? d - 360 : d
}

/** Point displaced by km along the north/east axes (equirectangular — fine at
 * city scale). Same formula as backend geometry.offset_km. */
export function offsetKm(p: Pt, northKm: number, eastKm: number): Pt {
  const kmPerDegLat = (Math.PI / 180) * 6371
  return {
    lat: p.lat + northKm / kmPerDegLat,
    lon: p.lon + eastKm / (kmPerDegLat * Math.cos((p.lat * Math.PI) / 180)),
  }
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
  const b = boundaryAt(lat, lon, boundaries)
  return b ? b.name_uk : null
}

/** Id of the raion whose polygon contains (lat, lon), or null — the client
 * twin of backend home_danger.raion_id_for_point. */
export function raionIdAt(
  lat: number,
  lon: number,
  boundaries: DistrictBoundary[],
): number | null {
  const b = boundaryAt(lat, lon, boundaries)
  return b ? b.id : null
}

function boundaryAt(
  lat: number,
  lon: number,
  boundaries: DistrictBoundary[],
): DistrictBoundary | null {
  for (const b of boundaries) {
    const polys =
      b.geojson.type === 'Polygon'
        ? [b.geojson.coordinates]
        : b.geojson.coordinates
    for (const rings of polys) {
      // First ring is the outer boundary; ignore holes for this coarse check.
      if (inRing(lat, lon, rings[0] as number[][])) return b
    }
  }
  return null
}
