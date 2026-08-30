import type { RawSource, Region } from '@/types'

/** The sources worth offering while `regions` are picked: the channels BOUND to
 * one of them (primary or extra — `RawSourceOut.regions`).
 *
 * Bindings, not where a message landed: a source never pins a place outside
 * them, so they are exactly the set of channels that can produce anything in
 * the picked oblasts. An empty pick is the filter's off position and offers
 * everything.
 */
export function sourcesInRegions(sources: RawSource[], regions: Region[]): RawSource[] {
  if (regions.length === 0) return sources
  return sources.filter((s) => s.regions.some((r) => regions.includes(r)))
}
