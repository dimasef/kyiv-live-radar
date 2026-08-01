import { launcherGlyphSvg, threatGlyphSvg } from '@/threatIcons'
import type { ThreatAxis } from '@/types'

import AxisLabel, { WRAP } from './AxisLabel'

/** On-screen state: the type glyph over a SOFT blurred zone at the source's
 * representative centroid — deliberately fuzzy, because an origin is a whole
 * oblast/sea, not a precise point (see origins.py). */
export default function AxisSourceMarker({
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
  // A ballistic axis's source IS a ground launcher (ОТРК), so the origin marker
  // shows the launch glyph — never the falling-ballistic glyph, which belongs
  // over the target, not the launch zone.
  const glyph =
    axis.target_type === 'ballistic'
      ? launcherGlyphSvg({ color, size: 26 })
      : threatGlyphSvg(axis.target_type, { color, size: 26 })
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
          dangerouslySetInnerHTML={{ __html: glyph }}
        />
      </div>
      <AxisLabel axis={axis} color={color} />
    </div>
  )
}
