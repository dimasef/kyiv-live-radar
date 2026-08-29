import { effectiveRegion, homeRegion, regionLabel } from '@/lib/regions'
import type { Region, RegionInfo } from '@/types'

/** The name of the region the journal is actually about, when that is NOT the
 * one this reader follows — else null.
 *
 * The journal is aggregated server-side over the deployment's home region
 * alone (backend api/journal_window.py: northern tracks are early warning, not
 * nights this city lived through). Nothing on the page says so, so for a reader
 * following another oblast every figure on it silently belongs to someone else.
 *
 * Null while the catalogue has not arrived: with no home region known there is
 * no name to show and no comparison to make, and blocking the page on data that
 * has not loaded yet would be worse than showing it.
 */
export function foreignJournalRegion(
  catalogue: RegionInfo[],
  chosen: Region | null,
): string | null {
  const home = homeRegion(catalogue)
  if (home === null) return null
  const followed = effectiveRegion(catalogue, chosen)
  return followed === null || followed === home ? null : regionLabel(catalogue, home)
}
