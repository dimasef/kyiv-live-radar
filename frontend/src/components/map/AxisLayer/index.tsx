import type { Map as LeafletMap } from 'leaflet'
import { useEffect, useReducer } from 'react'

import { useRadar } from '@/store'
import { TYPE_COLORS } from '@/theme'
import type { ThreatAxis } from '@/types'

import { isWellInsideView } from '../edgeProjection'
import AxisSourceMarker from './AxisSourceMarker'
import AxisWedge from './AxisWedge'

/** One axis, rendered viewport-aware: a source marker at the origin's real
 * location once the operator has zoomed out enough to see it, otherwise the
 * edge wedge. Both are always mounted (for axes that have coords) so crossing
 * the boundary crossfades instead of popping. Bare-sector axes (no origin) stay
 * edge-only — a direction with no place can't be placed. */
function AxisIndicator({ axis, map }: { axis: ThreatAxis; map: LeafletMap }) {
  const color = TYPE_COLORS[axis.target_type] ?? TYPE_COLORS.unknown
  const hasCoords = axis.origin_lat != null && axis.origin_lon != null

  let inView = false
  let x = -9999
  let y = -9999
  if (hasCoords) {
    const pt = map.latLngToContainerPoint([axis.origin_lat as number, axis.origin_lon as number])
    x = pt.x
    y = pt.y
    inView = isWellInsideView(x, y, map.getSize())
  }

  return (
    <>
      <AxisWedge axis={axis} color={color} visible={!inView} />
      {hasCoords && <AxisSourceMarker axis={axis} color={color} x={x} y={y} visible={inView} />}
    </>
  )
}

/** Directional-axis layer: honest that these are a DIRECTION, not a placed point
 * — until the source itself is on screen, where the wedge morphs into a soft
 * source marker ("ось звідки летить"). Screen-space overlay projected against
 * the live Leaflet viewport, so it re-lays out on every pan/zoom. */
export default function AxisLayer({ map }: { map: LeafletMap | null }) {
  const axes = useRadar((s) => s.axes)
  const [, rerender] = useReducer((n: number) => n + 1, 0)

  // Re-project on every viewport change — the only thing outside React we sync to.
  useEffect(() => {
    if (map == null) return
    const onViewChange = () => rerender()
    map.on('move zoom viewreset resize zoomanim', onViewChange)
    return () => {
      map.off('move zoom viewreset resize zoomanim', onViewChange)
    }
  }, [map])

  if (map == null || axes.length === 0) return null
  return (
    <>
      {axes.map((a) => (
        <AxisIndicator key={a.id} axis={a} map={map} />
      ))}
    </>
  )
}
