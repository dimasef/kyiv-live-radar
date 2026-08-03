import type { ThreatAxis } from '@/types'

import { edgePercent } from '../edgeProjection'
import AxisLabel, { WRAP } from './AxisLabel'

/** Off-screen state: a chevron on the map edge pointing along the inbound bearing. */
export default function AxisWedge({
  axis,
  color,
  visible,
}: {
  axis: ThreatAxis
  color: string
  visible: boolean
}) {
  const { left, top } = edgePercent(axis.bearing_deg)
  const corroborated = axis.status === 'corroborated'
  return (
    <div className={WRAP} style={{ left: `${left}%`, top: `${top}%`, opacity: visible ? 1 : 0 }}>
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
      <AxisLabel axis={axis} color={color} />
    </div>
  )
}
