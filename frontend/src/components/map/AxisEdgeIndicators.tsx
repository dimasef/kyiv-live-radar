import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import { TYPE_COLORS } from '../../theme'
import type { ThreatAxis } from '../../types'

/** Where a wedge sits on the container edge, in %, for a compass bearing.
 * Resolution-independent: intersect the ray from centre with the unit box. */
function edgePercent(bearingDeg: number): { left: number; top: number } {
  const rad = (bearingDeg * Math.PI) / 180
  const dx = Math.sin(rad) // east = +x
  const dy = -Math.cos(rad) // north = -y (screen y grows downward)
  // Scale the ray until it hits the nearest box edge from centre (0.5, 0.5).
  const tx = dx !== 0 ? 0.5 / Math.abs(dx) : Infinity
  const ty = dy !== 0 ? 0.5 / Math.abs(dy) : Infinity
  const t = Math.min(tx, ty) * 0.86 // inset so the wedge isn't clipped
  return { left: (0.5 + t * dx) * 100, top: (0.5 + t * dy) * 100 }
}

function AxisWedge({ axis }: { axis: ThreatAxis }) {
  const { t } = useTranslation()
  const { left, top } = edgePercent(axis.bearing_deg)
  const color = TYPE_COLORS[axis.target_type] ?? TYPE_COLORS.unknown
  const corroborated = axis.status === 'corroborated'
  const typeLabel = t(`target.${axis.target_type}`, axis.target_type)
  const origin = axis.origin_name ?? t(`axisSector.${axis.sector}`, axis.sector)

  return (
    <div
      className="pointer-events-none absolute z-[850] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
      style={{ left: `${left}%`, top: `${top}%` }}
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
      <div
        className="mt-0.5 whitespace-nowrap rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium leading-tight"
        style={{ color }}
      >
        {typeLabel} · {origin}
        {corroborated ? (
          <span className="ml-1 opacity-70">×{axis.corroboration_count}</span>
        ) : (
          <span className="ml-1 opacity-60">{t('axis.unverified')}</span>
        )}
      </div>
    </div>
  )
}

/** Screen-space wedges at the map edge for inbound directional axes — honest
 * that these are a DIRECTION, not a placed point (WORKFLOW.md threat-context
 * layer). Supplementary, volunteer-sourced; unverified axes are dashed/faded. */
export default function AxisEdgeIndicators() {
  const axes = useRadar((s) => s.axes)
  if (axes.length === 0) return null
  return (
    <>
      {axes.map((a) => (
        <AxisWedge key={a.id} axis={a} />
      ))}
    </>
  )
}
