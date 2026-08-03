import { Navigation } from 'lucide-react'
import type { Map as LeafletMap } from 'leaflet'
import { useEffect, useReducer } from 'react'
import { useTranslation } from 'react-i18next'

import MarkerGlyph from '@/components/common/MarkerGlyph'
import { homeStyleOf } from '@/lib/contactMarker'
import { haversineKm } from '@/lib/geo'
import { useRadar } from '@/store'

import { edgePercent, isWellInsideView, screenBearing } from './edgeProjection'

/** The zoom clicking the pointer lands on. City level, roughly what the map
 * opens at, rather than the street level controllers.tsx uses for a fresh
 * geolocation fix: this button answers "where am I relative to home", so it
 * should land with the city around it, not with home filling the screen.
 *
 * A floor, not a target — someone already closer in has panned there on
 * purpose and shouldn't be zoomed back out. */
const HOME_ZOOM = 10

function formatKm(km: number): string {
  return km < 10 ? km.toFixed(1) : String(Math.round(km))
}

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
  // Home is on screen — nothing to point at. The same margin as the axis wedges
  // use, so a marker halfway off the edge doesn't count as visible.
  if (isWellInsideView(point.x, point.y, size)) return null

  const bearing = screenBearing(point.x - size.x / 2, point.y - size.y / 2)
  const { left, top } = edgePercent(bearing)
  const centre = map.getCenter()
  const km = haversineKm({ lat: centre.lat, lon: centre.lng }, { lat: home.lat, lon: home.lon })

  return (
    <button
      onClick={() => map.flyTo([home.lat, home.lon], Math.max(map.getZoom(), HOME_ZOOM))}
      title={t('home.backToHome')}
      aria-label={t('home.backToHome')}
      className="pointer-events-auto absolute z-[860] flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 rounded-full border bg-black/75 px-2 py-1 backdrop-blur-sm transition-transform hover:scale-105"
      style={{ left: `${left}%`, top: `${top}%`, borderColor: `${style.color}66` }}
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
  )
}
