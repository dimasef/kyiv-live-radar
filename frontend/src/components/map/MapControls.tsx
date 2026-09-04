import FullscreenButton from './FullscreenButton'
import ImpactLayerButton from './ImpactLayerButton'
import MapLegend from './MapLegend'
import ZoneLayerButton from './ZoneLayerButton'

/** The bottom-left cluster floating over the map, above leaflet's own UI. The
 * raised bottom offset clears the mobile bottom sheet; on lg the sheet is gone.
 *
 * Every control here is a 40px button and stays one: anything with a panel opens
 * it upward over the map as a popover (see MapLegend), so the row keeps its
 * width and no button moves out from under the cursor when another is used. */
export default function MapControls() {
  return (
    <div className="pointer-events-auto absolute bottom-[4.2rem] left-3 z-[900] flex items-end gap-2 lg:bottom-3">
      <MapLegend />
      <ZoneLayerButton />
      <ImpactLayerButton />
      <FullscreenButton />
    </div>
  )
}
