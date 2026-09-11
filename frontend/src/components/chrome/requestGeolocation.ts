import { insideWatchedRegions } from '@/lib/regions'
import { useRadar } from '@/store'

/** Why a location request produced no home. 'implausible' is the interesting
 * one: the browser answered, confidently, with a point outside every watched
 * region — the signature of a jammed GNSS fix during a raid. */
export type GeoFailure = 'denied' | 'implausible'

/** Request the browser geolocation and set it as home (origin 'geo'), unless
 * the fix lands somewhere the reader could not plausibly live.
 *
 * Only ever called from the button. Nothing in the app asks for a location on
 * its own — see the note in store/bootstrap.ts. */
export function requestGeolocation(onFail?: (reason: GeoFailure) => void) {
  if (!('geolocation' in navigator)) {
    onFail?.('denied')
    return
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude: lat, longitude: lon } = pos.coords
      const state = useRadar.getState()
      if (!insideWatchedRegions(state.regions, lat, lon)) {
        onFail?.('implausible')
        return
      }
      state.setHome({ lat, lon, radiusKm: state.home?.radiusKm ?? 3, origin: 'geo' })
    },
    () => onFail?.('denied'),
    { enableHighAccuracy: true, timeout: 8000 },
  )
}
