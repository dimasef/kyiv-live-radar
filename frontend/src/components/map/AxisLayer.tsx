import type { Map as LeafletMap } from 'leaflet'
import { useEffect, useReducer } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import { TYPE_COLORS } from '../../theme'
import { threatGlyphSvg } from '../../threatIcons'
import type { ThreatAxis } from '../../types'

// The origin counts as "on screen" only once it's this many px inside the edge —
// right at the border a wedge still reads better than a half-clipped marker.
const VIEW_MARGIN_PX = 56

/** Where a wedge sits on the container edge, in %, for a compass bearing.
 * Resolution-independent: intersect the ray from centre with the unit box. */
function edgePercent(bearingDeg: number): { left: number; top: number } {
  const rad = (bearingDeg * Math.PI) / 180
  const dx = Math.sin(rad) // east = +x
  const dy = -Math.cos(rad) // north = -y (screen y grows downward)
  const tx = dx !== 0 ? 0.5 / Math.abs(dx) : Infinity
  const ty = dy !== 0 ? 0.5 / Math.abs(dy) : Infinity
  const t = Math.min(tx, ty) * 0.86 // inset so the wedge isn't clipped
  return { left: (0.5 + t * dx) * 100, top: (0.5 + t * dy) * 100 }
}

function AxisLabel({ axis, color }: { axis: ThreatAxis; color: string }) {
  const { t } = useTranslation()
  const typeLabel = t(`target.${axis.target_type}`, axis.target_type)
  const origin = axis.origin_name ?? t(`axisSector.${axis.sector}`, axis.sector)
  const corroborated = axis.status === 'corroborated'
  return (
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
  )
}

const WRAP =
  'pointer-events-none absolute z-[850] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center transition-opacity duration-300'

/** Off-screen state: a chevron on the map edge pointing along the inbound bearing. */
function AxisWedge({ axis, color, visible }: { axis: ThreatAxis; color: string; visible: boolean }) {
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

/** On-screen state: the type glyph over a SOFT blurred zone at the source's
 * representative centroid — deliberately fuzzy, because an origin is a whole
 * oblast/sea, not a precise point (see origins.py). */
function AxisSourceMarker({
  axis,
  color,
  x,
  y,
  visible,
}: {
  axis: ThreatAxis
  color: string
  x: number
  y: number
  visible: boolean
}) {
  const corroborated = axis.status === 'corroborated'
  return (
    <div className={WRAP} style={{ left: `${x}px`, top: `${y}px`, opacity: visible ? 1 : 0 }}>
      <div className="relative flex items-center justify-center">
        <span
          className="absolute rounded-full"
          style={{
            width: 76,
            height: 76,
            background: `radial-gradient(closest-side, ${color}40, ${color}00 72%)`,
            filter: 'blur(2px)',
          }}
        />
        <span
          style={{ filter: `drop-shadow(0 0 5px ${color})`, opacity: corroborated ? 1 : 0.55 }}
          dangerouslySetInnerHTML={{ __html: threatGlyphSvg(axis.target_type, { color, size: 26 }) }}
        />
      </div>
      <AxisLabel axis={axis} color={color} />
    </div>
  )
}

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
    const size = map.getSize()
    x = pt.x
    y = pt.y
    inView =
      pt.x >= VIEW_MARGIN_PX &&
      pt.x <= size.x - VIEW_MARGIN_PX &&
      pt.y >= VIEW_MARGIN_PX &&
      pt.y <= size.y - VIEW_MARGIN_PX
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
