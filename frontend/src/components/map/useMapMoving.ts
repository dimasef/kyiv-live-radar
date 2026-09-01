import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

/** Flags the map container for as long as a drag or a zoom is in flight, so
 * expensive decoration can switch itself off for the duration (`.map-moving`
 * in index.css).
 *
 * A CSS class rather than React state, deliberately: the paths must not unmount
 * and remount around a pan. They carry entry animations, and remounting them
 * would end every drag in a fade-in. This writes one attribute on one element
 * and re-renders nothing.
 */
export function useMapMoving(): void {
  const map = useMap()
  useEffect(() => {
    const root = map.getContainer()
    const on = () => root.classList.add('map-moving')
    const off = () => root.classList.remove('map-moving')
    map.on('movestart', on)
    map.on('zoomstart', on)
    map.on('moveend', off)
    map.on('zoomend', off)
    return () => {
      map.off('movestart', on)
      map.off('zoomstart', on)
      map.off('moveend', off)
      map.off('zoomend', off)
      off()
    }
  }, [map])
}
