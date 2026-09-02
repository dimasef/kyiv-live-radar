import { useMemo } from 'react'

import { useRadar } from '@/store'
import type { AlertZone } from '@/types'

import { withOfficialKyiv } from './alertZones'

/** The siren state the layer actually paints: the district provider's roster,
 * with Kyiv city taken from the official channel instead (see
 * `withOfficialKyiv`).
 *
 * A hook rather than three call sites reading `s.zones`, for the same reason
 * `inShownRegions` is one function: the polygons, the count badge and the
 * auto-frame have to agree, and they only ever agreed because they all read the
 * same raw map. Overriding one zone in only one of them would put the
 * disagreement back somewhere less visible.
 */
export function useZoneStates(): Record<string, AlertZone> {
  const zones = useRadar((s) => s.zones)
  const alerts = useRadar((s) => s.alerts)
  const feedOk = useRadar((s) => s.feedOk)
  return useMemo(() => withOfficialKyiv(zones, alerts, feedOk), [zones, alerts, feedOk])
}
