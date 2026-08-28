import L from 'leaflet'
import { useEffect } from 'react'
import { GeoJSON, Popup, useMap } from 'react-leaflet'

import { currentRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import { isInFeed, isPinnedRegion } from '@/store/feedRegions'

import { REGION_LAYER_MAX_ZOOM } from '../constants'
import { tagPath } from '../tagPath'
import { useMapZoom } from '../useMapZoom'
import RegionMenu from './RegionMenu'
import { regionStyle } from './regionStyle'

const REGION_ATTR = 'data-region'

/** Oblast outlines, and the menu that adds one to the event feed.
 *
 * Only drawn once the map is zoomed out past the point where a raion is legible
 * (ZONE_FIT_MIN_ZOOM documents where that is) — at city zoom an oblast outline
 * is off-screen anyway, and its hit area would swallow clicks meant for the map.
 *
 * Three constraints on the click, all load-bearing:
 *  - `placingHome` wins. MapView unmounts this layer while home placement is
 *    armed, so a popup can never block the click that gesture is waiting for.
 *  - Leaflet bubbles clicks to the map from paths (but not from markers) — see
 *    InspectController, which reads that bubble as "clear the inspection". Left
 *    alone, clicking an oblast would also drop the track being read, so the
 *    handler stops propagation.
 *  - Mounted AFTER AlertZoneLayer, so when both are on at this zoom the oblast
 *    is the shape that receives the click. Its fill is a hit area, not a colour
 *    (see regionStyle), so it costs nothing visually to be on top.
 */
export default function RegionLayer() {
  const map = useMap()
  const zoom = useMapZoom(map)
  const regions = useRadar((s) => s.regions)
  const outlines = useRadar((s) => s.regionOutlines)
  const ensureRegionOutlines = useRadar((s) => s.ensureRegionOutlines)
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const noteRegionLayerSeen = useRadar((s) => s.noteRegionLayerSeen)
  // The region the reader FOLLOWS — see store/feedRegions.isPinnedRegion.
  const followed = useRadar((s) => currentRegion(s))

  const visible = zoom != null && zoom <= REGION_LAYER_MAX_ZOOM

  // Entering the band is a moment, not a render: it lazily pulls the polygons
  // and raises the one-time hint, both of which write to the store. Doing that
  // inline would be a state update during another component's render.
  useEffect(() => {
    if (!visible) return
    ensureRegionOutlines()
    noteRegionLayerSeen()
  }, [visible, ensureRegionOutlines, noteRegionLayerSeen])

  if (!visible) return null

  return (
    <>
      {regions.map((region) => {
        const shape = outlines[region.id]
        if (!shape) return null
        const inFeed = isInFeed(region.id, feedExtraRegions, followed)
        const pinned = isPinnedRegion(region.id, followed)
        return (
          <GeoJSON
            // Remount on a state change so the new style is applied — Leaflet
            // caches the path options it was created with.
            key={`${region.id}-${inFeed}-${pinned}`}
            data={shape.geojson}
            ref={(layer) => tagPath(layer, REGION_ATTR, region.id)}
            style={regionStyle({ isHome: pinned, inFeed, active: region.active })}
            eventHandlers={{ click: (e) => L.DomEvent.stopPropagation(e) }}
          >
            <Popup>
              <RegionMenu region={region} />
            </Popup>
          </GeoJSON>
        )
      })}
    </>
  )
}
