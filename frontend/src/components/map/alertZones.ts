import type { Alert, AlertZone, AlertZoneGeometry, Region } from '@/types'

/** The one raion whose siren does NOT come from the district provider. */
export const KYIV_CITY_ZONE_ID = 'kyiv-city'

/** Repaint Kyiv city from the official channel instead of the district
 * provider, so the map and the banner can never contradict each other.
 *
 * They used to. The banner takes Kyiv's siren from the official channel (which
 * is why nothing writes a `kyiv-city` alert from the provider — see the
 * backend's `zone_alerts.eligible`), while the layer painted the same city from
 * the provider. Two sources, one screen: the polygon could sit red with the
 * banner silent, or the other way round, and there was no way for a reader to
 * know which half to believe.
 *
 * The three cases are not symmetric, and that is the whole design:
 *  - listener up  → the channel is the answer, including its own start time, so
 *    the label counts from when the siren was actually announced.
 *  - listener DOWN → `stale`, never `clear`. We know nothing about Kyiv, and
 *    rendering that as «відбій» is the one failure this layer exists to avoid.
 *  - no Telegram at all (`null` — simulator, replay, a dev box) → leave the
 *    provider's state alone. There is no better source to prefer, and blanking
 *    the capital on every dev run would be a worse lie than the disagreement
 *    this function removes.
 */
export function withOfficialKyiv(
  zones: Record<string, AlertZone>,
  alerts: Alert[],
  feedOk: boolean | null,
): Record<string, AlertZone> {
  const base = zones[KYIV_CITY_ZONE_ID]
  if (!base || feedOk === null) return zones
  if (feedOk === false) {
    return { ...zones, [KYIV_CITY_ZONE_ID]: { ...base, stale: true } }
  }
  const city = alerts.filter((a) => a.scope === 'city' && a.region === 'kyiv' && a.zone_id == null)
  const open = city.find((a) => !a.ended_at)
  // `/alerts/recent` is newest-first, so the first ended one is the last відбій
  // — what a quiet city counts "clear for N" from.
  const ended = city.find((a) => a.ended_at)
  return {
    ...zones,
    [KYIV_CITY_ZONE_ID]: {
      ...base,
      stale: false,
      alert: open != null,
      changed_at: open ? open.started_at : (ended?.ended_at ?? null),
    },
  }
}

/** Narrow a zone map — state or geometry — to the regions the reader follows.
 *
 * The layer paints four oblasts' raions, of which a reader watches one or two.
 * Sirens over Харківщина are not context for someone in Сумщина, they are
 * noise on top of the picture they came for, and the layer's own count badge
 * would announce raions the map is not showing.
 *
 * Everything the layer does goes through this: the polygons, the badge and the
 * auto-frame. That is the point of it being one function — the three used to
 * agree only because they all saw everything.
 */
export function inShownRegions<T extends { region: Region }>(
  byId: Record<string, T>,
  shown: ReadonlySet<Region>,
): Record<string, T> {
  return Object.fromEntries(Object.entries(byId).filter(([, v]) => shown.has(v.region)))
}

/** How a zone should be painted. `stale` is its own tone on purpose: when the
 * provider is unreachable we know nothing, and drawing that as "відбій" would
 * turn an outage into a false all-clear. */
export type ZoneTone = 'alert' | 'clear' | 'stale'

export function zoneTone(zone: AlertZone): ZoneTone {
  if (zone.stale) return 'stale'
  return zone.alert ? 'alert' : 'clear'
}

/** How long the zone has held its current state, split into hours+minutes.
 * Null when the provider never reported a transition for it, or when its
 * timestamp is in the future (a clock disagreement — better to say nothing). */
export function sinceParts(
  changedAt: string | null | undefined,
  nowMs: number,
): { h: number; m: number } | null {
  if (!changedAt) return null
  const began = Date.parse(changedAt)
  if (Number.isNaN(began)) return null
  const minutes = Math.floor((nowMs - began) / 60_000)
  if (minutes < 0) return null
  return { h: Math.floor(minutes / 60), m: minutes % 60 }
}

/** Which i18n key and values render the always-on centre label's duration.
 *
 * One unit, never two: this sits over the map permanently on every raion, so it
 * gets "40хв" or "2г" where the hover caption can afford «1 год 20 хв». Under an
 * hour the minutes are the whole answer; past it they stop mattering — nobody
 * acts differently on a siren that has run 1:20 versus 1:35, and the extra
 * digits are two more characters to read past on a screenful of labels at once.
 *
 * Rounded, not truncated: 1 h 50 min is "2г", because floor would call it "1г"
 * for the better part of an hour and read as newer than it is. */
export function compactSinceLabel(
  since: { h: number; m: number } | null,
): { key: 'zones.compactH' | 'zones.compactM'; vars: Record<string, number> } | null {
  if (!since) return null
  if (since.h > 0) {
    return { key: 'zones.compactH', vars: { h: since.h + (since.m >= 30 ? 1 : 0) } }
  }
  return { key: 'zones.compactM', vars: { m: since.m } }
}

/** Zones under alert, most recent first — what a "N raions under siren" summary
 * would read off. */
export function alertedZones(zones: Record<string, AlertZone>): AlertZone[] {
  return Object.values(zones)
    .filter((z) => z.alert && !z.stale)
    .sort((a, b) => (b.changed_at ?? '').localeCompare(a.changed_at ?? ''))
}

/** South-west / north-east corner of everything the layer LIGHTS UP, in
 * Leaflet's [lat, lon] order — the box the view has to take in for the siren
 * picture to be readable at a glance.
 *
 * Alerted raions when there are any, otherwise the whole watched area: with
 * nothing sounding, "the layer" IS all of it, and framing one arbitrary quiet
 * raion would be worse than framing the lot.
 *
 * Null when there is nothing to frame — the polygons load lazily on the first
 * switch-on, so an empty geometry means "not here yet", not "nowhere". */
export function zoneFitBounds(
  geometry: AlertZoneGeometry,
  zones: Record<string, AlertZone>,
): [[number, number], [number, number]] | null {
  const lit = Object.keys(geometry).filter((id) => zones[id] && zoneTone(zones[id]) === 'alert')
  const ids = lit.length > 0 ? lit : Object.keys(geometry)
  let south = Infinity
  let west = Infinity
  let north = -Infinity
  let east = -Infinity
  for (const id of ids) {
    const shape = geometry[id].geojson
    // GeoJSON nests one level deeper for a MultiPolygon, and positions are
    // [lon, lat] — the opposite order to everything Leaflet is handed.
    const polygons = shape.type === 'Polygon' ? [shape.coordinates] : shape.coordinates
    for (const rings of polygons) {
      for (const ring of rings) {
        for (const [lon, lat] of ring) {
          if (lat < south) south = lat
          if (lat > north) north = lat
          if (lon < west) west = lon
          if (lon > east) east = lon
        }
      }
    }
  }
  return Number.isFinite(south) ? [[south, west], [north, east]] : null
}
