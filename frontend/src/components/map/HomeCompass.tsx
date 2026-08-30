import { Navigation } from 'lucide-react'
import type { Map as LeafletMap } from 'leaflet'
import { useEffect, useReducer } from 'react'
import { useTranslation } from 'react-i18next'

import MarkerGlyph from '@/components/common/MarkerGlyph'
import { homeStyleOf } from '@/lib/contactMarker'
import { formatKm, haversineKm } from '@/lib/geo'
import { useRadar } from '@/store'

import {
  edgeMarkerPosition,
  isInsideBox,
  outsetInsets,
  overlayInsets,
  screenBearing,
  visibleInsets,
} from './edgeProjection'

/** The zoom clicking the pointer lands on. City level, roughly what the map
 * opens at, rather than the street level controllers.tsx uses for a fresh
 * geolocation fix: this button answers "where am I relative to home", so it
 * should land with the city around it, not with home filling the screen.
 *
 * A floor, not a target — someone already closer in has panned there on
 * purpose and shouldn't be zoomed back out. */
const HOME_ZOOM = 10

/** Nominal pill footprint, slightly generous — it only decides how far from a
 * corner the pill stops, and overshooting there costs nothing. */
const PILL = { width: 108, height: 30 }

/** How far PAST the visible box home has to travel before the pointer appears,
 * as a share of the shorter viewport side.
 *
 * Two jobs, both learned the hard way. `visibleInsets` pads every edge out to
 * VIEW_MARGIN_PX so an edge marker never sits half-clipped — correct for an axis
 * wedge, which REPLACES the origin it points at, but on its own it made this
 * pill appear for a home still sitting plainly on screen, quoting a distance to
 * something the operator could see. And a boundary with no dead zone flickers:
 * dragging home a few pixels back and forth across the edge popped the pill in
 * and out under the finger.
 *
 * A ratio rather than a px count so "home is well off to the side" reads the
 * same on a phone and on a desktop. It is measured from the SAFE box, which is
 * already inset, so the dead zone past the real container edge is what's left
 * over: ~70 px on a phone, ~250 px on a desktop. */
const APPEAR_MARGIN_RATIO = 0.35


/** Points back to the user's home once they've panned or zoomed away from it,
 * and takes them there when clicked.
 *
 * It carries the home marker's own icon and colour on purpose: threat axes put
 * their own wedges on this same edge, and a bare arrow among them would be one
 * more thing to decode during an alert.
 *
 * Screen-space overlay projected against the live viewport, like AxisLayer —
 * the map is genuinely outside React, so it's re-laid out from map events. */
export default function HomeCompass({ map }: { map: LeafletMap | null }) {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const style = homeStyleOf(useRadar((s) => s.homeStyle))
  const [, rerender] = useReducer((n: number) => n + 1, 0)

  useEffect(() => {
    if (map == null) return
    const onViewChange = () => rerender()
    map.on('move zoom viewreset resize zoomanim', onViewChange)
    return () => {
      map.off('move zoom viewreset resize zoomanim', onViewChange)
    }
  }, [map])

  if (map == null || home == null) return null

  const point = map.latLngToContainerPoint([home.lat, home.lon])
  const size = map.getSize()
  const insets = overlayInsets()
  // Nothing to point at until home is off screen AND well clear of it. The box
  // still starts from the safe area, so a home tucked under the feed sheet or
  // the alert banner counts as gone even though it is technically in frame.
  const gone = !isInsideBox(
    point.x,
    point.y,
    size,
    outsetInsets(visibleInsets(insets), APPEAR_MARGIN_RATIO * Math.min(size.x, size.y)),
  )
  if (!gone) return null

  const bearing = screenBearing(point.x - size.x / 2, point.y - size.y / 2)
  const { left, top } = edgeMarkerPosition(bearing, size, insets, PILL)
  const centre = map.getCenter()
  const km = haversineKm({ lat: centre.lat, lon: centre.lng }, { lat: home.lat, lon: home.lon })

  return (
    <div className="pointer-events-none absolute z-[860]" style={{ left, top }}>
      <button
        onClick={() => map.flyTo([home.lat, home.lon], Math.max(map.getZoom(), HOME_ZOOM))}
        title={t('home.backToHome')}
        aria-label={t('home.backToHome')}
        className="pointer-events-auto flex items-center gap-1.5 whitespace-nowrap rounded-full border bg-black/75 px-2 py-1 backdrop-blur-sm transition-transform hover:scale-105"
        style={{ borderColor: `${style.color}66` }}
      >
        <Navigation
          size={13}
          style={{ color: style.color, transform: `rotate(${bearing}deg)` }}
          fill="currentColor"
        />
        <MarkerGlyph icon={style.icon} color={style.color} size={14} glow={false} />
        <span className="font-mono text-[10px] leading-none text-slate-300">
          {formatKm(km)} {t('home.km')}
        </span>
      </button>
    </div>
  )
}
