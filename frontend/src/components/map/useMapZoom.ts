import type L from 'leaflet'
import { useEffect, useState } from 'react'

/** The map's current zoom level as React state.
 *
 * A `useEffect` here is the intended kind, for the same reason useMapViewport
 * gives: Leaflet owns the viewport and announces changes through its own event
 * emitter.
 *
 * Deliberately NOT a field on useMapViewport — that hook's value feeds
 * viewportCull, so adding zoom to it would re-cull every threat on each step of
 * a zoom gesture. This one only ever moves when the level does, so a pan costs
 * nothing.
 *
 * Null until the map exists; callers must treat that as "level unknown".
 */
export function useMapZoom(map: L.Map | null): number | null {
  const [zoom, setZoom] = useState<number | null>(null)

  useEffect(() => {
    if (!map) return
    const read = () => setZoom(map.getZoom())
    read()
    map.on('zoomend', read)
    return () => {
      map.off('zoomend', read)
    }
  }, [map])

  return zoom
}
