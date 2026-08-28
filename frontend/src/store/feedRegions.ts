import type { Region, RegionInfo } from '@/types'

/** Which watched regions the event feed lists, and how that survived the move
 * from one boolean to a set. Pure — the slice does the storage I/O.
 */

/** The set the legacy boolean meant when it was written. A historical constant,
 * not configuration: 'klr-feed-other-regions' could only ever mean "Чернігівщина
 * too", because that was the only other region that existed. */
const LEGACY_ALL: Region[] = ['chernihiv']

/** Read the stored extra regions, falling back to what the old boolean meant.
 * `saved` is the new JSON array, `legacy` the old '0'/'1'. */
export function migrateFeedRegions(saved: string | null, legacy: string | null): Region[] {
  if (saved != null) {
    try {
      const parsed: unknown = JSON.parse(saved)
      if (Array.isArray(parsed)) return parsed.filter((id): id is Region => typeof id === 'string')
    } catch {
      // Corrupt value — fall through to the legacy reading rather than to [],
      // which would silently hide a region the reader had chosen to see.
    }
  }
  return legacy === '0' ? [] : LEGACY_ALL
}

/** Drop ids the server doesn't declare (a region retired, or a value left by a
 * newer build). One stale id would 422 the whole /events/recent page, and
 * bootstrap swallows that into a silently empty feed. No-op until the catalogue
 * has loaded — an empty catalogue is "unknown", not "nothing exists". */
export function pruneFeedRegions(extra: Region[], catalogue: RegionInfo[]): Region[] {
  if (catalogue.length === 0) return extra
  const known = new Set(catalogue.map((r) => r.id))
  return extra.filter((id) => known.has(id))
}

/** Every region the feed should show: the followed one plus the chosen extras.
 * Derived, not stored — that is what makes "the followed region is always shown"
 * impossible to violate rather than a rule some code path has to remember. */
export function shownRegions(extra: Region[], home: Region | null): Region[] {
  return home == null ? extra : [home, ...extra.filter((id) => id !== home)]
}

/** Whether the feed always lists this region and the reader has no "off" for it.
 *
 * The FOLLOWED region, never `RegionInfo.is_home`. Those two are the same thing
 * only for a reader who stayed on the deployment's own oblast, and the
 * difference is not cosmetic: `toggleFeedRegion` refuses to touch the followed
 * region, so a chip drawn from `is_home` renders the followed region as an
 * ordinary "off" chip that then does nothing when clicked. That shipped — a
 * reader who switched to Сумщина could not put Сумщина in their own feed
 * (2026-08-29).
 */
export function isPinnedRegion(id: Region, followed: Region | null): boolean {
  return id === followed
}

/** Whether this region's sightings reach the feed at all — pinned or added. */
export function isInFeed(id: Region, extra: Region[], followed: Region | null): boolean {
  return isPinnedRegion(id, followed) || extra.includes(id)
}
