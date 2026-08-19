import FullscreenButton from './FullscreenButton'
import MapLegend from './MapLegend'
import ZoneLayerButton from './ZoneLayerButton'

/** The bottom-left cluster floating over the map, above leaflet's own UI. The
 * raised bottom offset clears the mobile bottom sheet; on lg the sheet is gone.
 *
 * `items-end` so the fullscreen button stays level with the legend's own button
 * whether the legend is a 40px chip or an expanded panel. */
export default function MapControls() {
  return (
    <div className="pointer-events-auto absolute bottom-[4.2rem] left-3 z-[900] flex items-end gap-2 lg:bottom-3">
      <MapLegend />
      <ZoneLayerButton />
      <FullscreenButton />
    </div>
  )
}
