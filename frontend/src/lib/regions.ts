import type { Region, RegionInfo } from '@/types'

/** Pure lookups over the server-owned region catalogue (store.regions).
 *
 * The catalogue is empty until the boot fetch lands, and every one of these has
 * to render something sane before then — so each falls back to the raw id or to
 * "assume it's fine" rather than to a hardcoded region list, which is the thing
 * the catalogue exists to abolish.
 */

export function regionLabel(catalogue: RegionInfo[], id: Region | string): string {
  return catalogue.find((r) => r.id === id)?.name_uk ?? id
}

export function homeRegion(catalogue: RegionInfo[]): Region | null {
  return catalogue.find((r) => r.is_home)?.id ?? null
}

/** False only when the catalogue positively says the region has no data yet. */
export function regionIsActive(catalogue: RegionInfo[], id: Region | string): boolean {
  return catalogue.find((r) => r.id === id)?.active ?? true
}

/** The region the reader follows.
 *
 * Their explicit choice, falling back to the deployment's own until they have
 * made one — so the very first paint, before the picker is answered, shows the
 * home region rather than an empty feed and a map framed on nothing.
 */
export function effectiveRegion(
  catalogue: RegionInfo[],
  chosen: Region | null,
): Region | null {
  return chosen ?? homeRegion(catalogue)
}

/** `effectiveRegion` read straight off the store. Takes a structural shape
 * rather than RadarState so this module stays free of store imports. */
export function currentRegion(s: {
  regions: RegionInfo[]
  chosenRegion: Region | null
}): Region | null {
  return effectiveRegion(s.regions, s.chosenRegion)
}

/** What the MAP should be framed on: the region the reader picked, or
 * `fallback` (the whole country) when they have not picked one or the catalogue
 * has not answered yet.
 *
 * Reads `chosen` DIRECTLY rather than through `currentRegion`, and that
 * difference is the point. For the feed and for push, "no choice yet" has to
 * mean the deployment's own region — otherwise a first-run reader gets an empty
 * feed and no notifications. For the map it must not: framing an unanswered
 * picker on one oblast hides the other four behind the edge of the screen, and
 * the whole country is both the honest answer and the one that makes the picker
 * obvious.
 */
export function framingBounds(
  catalogue: RegionInfo[],
  chosen: Region | null,
  fallback: [[number, number], [number, number]],
): [[number, number], [number, number]] {
  return regionBounds(catalogue, chosen) ?? fallback
}

/** Whether a point falls inside any watched region — the sanity check on a
 * GNSS fix before it is allowed to become someone's home.
 *
 * Jamming is routine over Ukraine during a raid, and a jammed fix arrives
 * looking exactly like a good one: no error, a plausible accuracy, coordinates
 * in another country. The bounding boxes are coarse on purpose — this is not
 * asking "is this the right building", only "could the reader conceivably live
 * here", which is the only question a coordinate can be wrong about by a
 * thousand kilometres.
 *
 * Fails CLOSED on an unloaded catalogue, unlike its neighbours above: they fall
 * back to "assume it's fine" because the cost is a label rendering as an id,
 * while the cost here is a home marker somewhere the reader has never been.
 */
export function insideWatchedRegions(
  catalogue: RegionInfo[],
  lat: number,
  lon: number,
): boolean {
  return catalogue.some(({ bbox }) => {
    const [south, west, north, east] = bbox
    return bbox.length === 4 && lat >= south && lat <= north && lon >= west && lon <= east
  })
}

export function regionBounds(
  catalogue: RegionInfo[],
  id: Region | null,
): [[number, number], [number, number]] | null {
  const bbox = catalogue.find((r) => r.id === id)?.bbox
  if (!bbox || bbox.length !== 4) return null
  return [
    [bbox[0], bbox[1]],
    [bbox[2], bbox[3]],
  ]
}
