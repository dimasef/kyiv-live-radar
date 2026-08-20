import type L from 'leaflet'
import { useEffect, useState } from 'react'
import { GeoJSON, Tooltip, useMap } from 'react-leaflet'

import { useRadar } from '@/store'

import { zoneTone } from './alertZones'
import { ZONE_GLOW, ZONE_LABEL_NUDGE, ZONE_STYLES } from './constants'
import ZoneGlowDefs from './ZoneGlowDefs'
import ZoneLabel from './ZoneLabel'

/** Tag a zone's rendered path so it can be focused and identified.
 *
 * Leaflet draws each polygon as a bare <svg:path>, which nothing can focus — so
 * on touch and on the TV remote, where there is no hover at all, a raion's name
 * was unreachable. A tabindex fixes all three input modes at once: it makes the
 * path a tab stop for a keyboard, a focus target for a remote, and (in every
 * browser we target) focused by a tap — without touching the click, which the
 * map already spends on panning and home placement.
 *
 * Idempotent, because an inline ref callback re-runs on every render. It only
 * sets attributes — the focus listener itself is delegated on the map container
 * below, so there is nothing here to attach twice or leak.
 *
 * `setAttribute`, not `dataset`: SVGElement.dataset is missing on the older
 * engines the TV target runs (see lib/observers for the same class of guard),
 * and there it would throw rather than degrade.
 */
const ZONE_ATTR = 'data-zone'

function tagPath(layer: L.GeoJSON | null, zoneId: string): void {
  layer?.eachLayer((child) => {
    const el = (child as L.Path).getElement?.()
    if (!el) return
    el.setAttribute('tabindex', '0')
    el.setAttribute(ZONE_ATTR, zoneId)
  })
}

function zoneOf(target: EventTarget | null): string | null {
  const el = target as Element | null
  return el?.getAttribute?.(ZONE_ATTR) ?? null
}

/** Official air-raid state of the raions of Київщина and Чернігівщина, from an
 * external provider (see backend feeds/alert_zones.py). Purely contextual: it
 * says where sirens are sounding, never where a target is. Rendered below the
 * Kyiv raion outlines so it reads as background, and only while the operator
 * has the layer switched on — the polygons are fetched lazily on that switch. */
export default function AlertZoneLayer() {
  const zones = useRadar((s) => s.zones)
  const geometry = useRadar((s) => s.zoneGeometry)
  const map = useMap()
  /** Zone whose name is currently revealed — hovered, or focused. */
  const [named, setNamed] = useState<string | null>(null)

  // Focus is delegated on the container rather than bound per polygon: the
  // paths are remounted whenever a zone changes tone (see the key below), and
  // per-layer listeners would have to be re-attached on every one of those.
  useEffect(() => {
    const root = map.getContainer()
    const onIn = (e: FocusEvent) => {
      const id = zoneOf(e.target)
      if (id) setNamed(id)
    }
    const onOut = (e: FocusEvent) => {
      const id = zoneOf(e.target)
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
            style={{ ...ZONE_GLOW.style, className: 'zone-glow' }}
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
            ref={(layer) => tagPath(layer, zoneId)}
            data={shape.geojson}
            style={{ ...ZONE_STYLES[tone], className: 'zone-hit' }}
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
              className="zone-label"
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
