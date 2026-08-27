import type L from 'leaflet'
import { useEffect, useState } from 'react'

import type { LatLonBox } from './viewportCull'

/** How much slack to keep around the visible rectangle, as a fraction of it.
 *
 * The box is only recomputed when the map SETTLES — subscribing to `move`
 * instead would re-render on every frame of a drag, which is the cost this
 * whole mechanism exists to avoid. So the margin has to cover what a normal
 * flick reveals before `moveend` fires; a third of a screen in each direction
 * does, and anything past that appears when the gesture stops, which is also
 * when the operator starts reading again. */
const PAD_RATIO = 0.35

/** The map's visible lat/lon rectangle, padded, as React state.
 *
 * A `useEffect` here is the intended kind: Leaflet owns the viewport and
 * announces changes through its own event emitter, which is exactly the
 * "something genuinely outside React" the convention carves out.
 *
 * Null until the map exists and has been read once — callers must treat that as
 * "cull nothing", never as "nothing is visible".
 */
export function useMapViewport(map: L.Map | null): LatLonBox | null {
  const [box, setBox] = useState<LatLonBox | null>(null)

  useEffect(() => {
    if (!map) return
    const read = () => {
      const b = map.getBounds().pad(PAD_RATIO)
      setBox((prev) => {
        const next = {
          south: b.getSouth(),
          west: b.getWest(),
          north: b.getNorth(),
          east: b.getEast(),
        }
        // Leaflet fires moveend for gestures that changed nothing (a tap that
        // registered as a drag, invalidateSize with the same box). Returning
        // the previous object keeps those from re-rendering the whole map.
        return prev &&
          prev.south === next.south &&
          prev.west === next.west &&
          prev.north === next.north &&
          prev.east === next.east
          ? prev
          : next
      })
    }
    read()
    // `resize` matters as much as the pan events here: ResizeHandler calls
    // invalidateSize() when the mobile sheet or the viewport bar reflows, and
    // that changes what is on screen without any map movement at all.
    map.on('moveend zoomend resize', read)
    return () => {
      map.off('moveend zoomend resize', read)
    }
  }, [map])

  return box
}
