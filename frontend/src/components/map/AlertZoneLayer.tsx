import { useEffect, useState } from 'react'
import { GeoJSON, Tooltip, useMap } from 'react-leaflet'

import { useRadar } from '@/store'

import { zoneTone } from './alertZones'
import { tagPath, taggedId } from './tagPath'
import { ZONE_ALL_CLEAR, ZONE_GLOW, ZONE_LABEL_NUDGE, ZONE_STYLES } from './constants'
import ZoneGlowDefs from './ZoneGlowDefs'
import ZoneLabel from './ZoneLabel'

const ZONE_ATTR = 'data-zone'

/** Official air-raid state of the raions of Київщина and Чернігівщина, from an
 * external provider (see backend feeds/alert_zones.py). Purely contextual: it
 * says where sirens are sounding, never where a target is. Rendered below the
 * Kyiv raion outlines so it reads as background, and only while the operator
 * has the layer switched on — the polygons are fetched lazily on that switch. */
export default function AlertZoneLayer() {
  const zones = useRadar((s) => s.zones)
  const geometry = useRadar((s) => s.zoneGeometry)
  const allClear = useRadar((s) => s.zoneAllClear)
  const map = useMap()
  /** Zone whose name is currently revealed — hovered, or focused. */
  const [named, setNamed] = useState<string | null>(null)

  // Focus is delegated on the container rather than bound per polygon: the
  // paths are remounted whenever a zone changes tone (see the key below), and
  // per-layer listeners would have to be re-attached on every one of those.
  useEffect(() => {
    const root = map.getContainer()
    const onIn = (e: FocusEvent) => {
      const id = taggedId(e.target, ZONE_ATTR)
      if (id) setNamed(id)
    }
    const onOut = (e: FocusEvent) => {
      const id = taggedId(e.target, ZONE_ATTR)
      if (id) setNamed((cur) => (cur === id ? null : cur))
    }
    root.addEventListener('focusin', onIn)
    root.addEventListener('focusout', onOut)
    return () => {
      root.removeEventListener('focusin', onIn)
      root.removeEventListener('focusout', onOut)
    }
  }, [map])

  const shapes = Object.entries(geometry)
  const toneOf = (zoneId: string) => (zones[zoneId] ? zoneTone(zones[zoneId]) : 'stale')

  return (
    <>
      <ZoneGlowDefs />
      {/* Every glow first, then every outline — not glow+outline per zone. In
          one pass a neighbour's glow lands on top of the border drawn just
          before it, and alerted raions are almost always neighbours. */}
      {shapes
        .filter(([zoneId]) => toneOf(zoneId) === 'alert')
        .map(([zoneId, shape]) => (
          <GeoJSON
            key={`glow-${zoneId}`}
            data={shape.geojson}
            style={{ ...ZONE_GLOW.style, className: 'zone-glow zone-enter' }}
          />
        ))}
      {/* «Відбій»: the raion has already gone quiet in every other layer — this
          is the announcement of the change, mounted by the store for exactly as
          long as its animation runs. A separate non-interactive path on purpose:
          folding it into the outline's className would rekey that path, and the
          permanent label riding on it would blink away with the flash. */}
      {shapes
        .filter(([zoneId]) => allClear[zoneId])
        .map(([zoneId, shape]) => (
          <GeoJSON
            key={`allclear-${zoneId}`}
            data={shape.geojson}
            style={{ ...ZONE_ALL_CLEAR.style, className: 'zone-allclear' }}
          />
        ))}
      {shapes.map(([zoneId, shape]) => {
        const tone = toneOf(zoneId)
        return (
          // Keyed by tone: Leaflet's setStyle doesn't re-apply a className or
          // dashArray on an existing path, so a state change needs a fresh
          // mount (same trick as CitywidePulse).
          <GeoJSON
            key={`${zoneId}-${tone}`}
            ref={(layer) => tagPath(layer, ZONE_ATTR, zoneId)}
            data={shape.geojson}
            style={{ ...ZONE_STYLES[tone], className: 'zone-hit zone-enter' }}
            eventHandlers={{
              mouseover: () => setNamed(zoneId),
              mouseout: () => setNamed((cur) => (cur === zoneId ? null : cur)),
            }}
          >
            {/* Permanent, so the raion's state is readable without asking for
                it. pointer-events stay off it (.zone-label) — a label sitting on
                the polygon must not shadow the polygon's own hover. */}
            <Tooltip
              permanent
              direction="center"
              className="zone-label zone-enter"
              offset={ZONE_LABEL_NUDGE[zoneId] ?? [0, 0]}
            >
              <ZoneLabel
                name={shape.name_uk}
                zone={zones[zoneId]}
                tone={tone}
                named={named === zoneId}
              />
            </Tooltip>
          </GeoJSON>
        )
      })}
    </>
  )
}
