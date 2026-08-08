import type { ThreatAxis } from '@/types'

import { edgeMarkerPosition, type EdgeInsets } from '../edgeProjection'
import AxisLabel, { WRAP_AT } from './AxisLabel'

/** Nominal wedge footprint: the chevron plus its label underneath. The label is
 * capped at LABEL_MAX_PX so a long origin ("Реактивний БПЛА · Чернігівщина ×2")
 * can't outgrow this and clip off a phone screen; the rest is truncated. */
const LABEL_MAX_PX = 168
const WEDGE = { width: LABEL_MAX_PX, height: 52 }

/** Off-screen state: a chevron on the map edge pointing along the inbound bearing. */
export default function AxisWedge({
  axis,
  color,
  visible,
  size,
  insets,
}: {
  axis: ThreatAxis
  color: string
  visible: boolean
  size: { x: number; y: number }
  insets: EdgeInsets
}) {
  const { left, top } = edgeMarkerPosition(axis.bearing_deg, size, insets, WEDGE)
  const corroborated = axis.status === 'corroborated'
  return (
    <div
      className={WRAP_AT}
      style={{ left, top, maxWidth: WEDGE.width, opacity: visible ? 1 : 0 }}
    >
      <svg
        width="26"
        height="26"
        viewBox="0 0 24 24"
        style={{
          transform: `rotate(${axis.bearing_deg}deg)`,
          filter: `drop-shadow(0 0 5px ${color})`,
          opacity: corroborated ? 1 : 0.55,
        }}
      >
        {/* A chevron pointing OUTWARD along the bearing (the inbound direction). */}
        <path
          d="M12 3 L20 19 L12 14 L4 19 Z"
          fill={color}
          stroke="#05080d"
          strokeWidth="0.8"
          strokeDasharray={corroborated ? undefined : '2 2'}
        />
      </svg>
      <AxisLabel axis={axis} color={color} className="max-w-full" />
    </div>
  )
}
