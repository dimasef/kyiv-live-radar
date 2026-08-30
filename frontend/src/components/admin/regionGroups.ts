import type { Region, RegionInfo } from '@/types'

export interface RegionBucket<T> {
  /** null while the catalogue hasn't loaded — render the items with no heading
   * rather than blanking the panel. */
  region: RegionInfo | null
  items: T[]
}

/** Split a management list into per-region buckets, in catalogue order.
 *
 * Empty buckets are dropped — unlike the Sources tab, which keeps the home one
 * so the add form has somewhere to point. Here a heading with nothing under it
 * says "no targets over Сумщина", which the absence of the heading already
 * says, and during a raid the operator is reading a list, not a table of
 * contents.
 *
 * A region the catalogue doesn't know (a stored row from before it was
 * declared) is kept in a trailing bucket rather than dropped: this list is the
 * place an operator cancels things, and something they cannot see is something
 * they cannot cancel.
 */
export function groupByRegion<T>(
  items: T[],
  catalogue: RegionInfo[],
  regionOf: (item: T) => Region | string,
): RegionBucket<T>[] {
  if (items.length === 0) return []
  if (catalogue.length === 0) return [{ region: null, items }]

  const buckets = catalogue
    .map((region) => ({ region, items: items.filter((i) => regionOf(i) === region.id) }))
    .filter((bucket) => bucket.items.length > 0)

  const known = new Set(catalogue.map((r) => r.id))
  const orphans = items.filter((i) => !known.has(regionOf(i) as Region))
  return orphans.length > 0 ? [...buckets, { region: null, items: orphans }] : buckets
}
