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
