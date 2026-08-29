import { useMemo } from 'react'

import { currentRegion } from '@/lib/regions'
import type { Region } from '@/types'

import { useRadar } from '.'
import { shownRegions } from './feedRegions'

/** The regions this reader follows: the chosen one plus the extras they added.
 *
 * The same set the event feed lists, deliberately — a map layer that answered a
 * different question ("the chosen region only", say) would show sirens for an
 * oblast whose sightings are in the feed, or hide ones whose are.
 */
export function useShownRegions(): ReadonlySet<Region> {
  const regions = useRadar((s) => s.regions)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  return useMemo(
    () => new Set(shownRegions(feedExtraRegions, currentRegion({ regions, chosenRegion }))),
    [feedExtraRegions, regions, chosenRegion],
  )
}
