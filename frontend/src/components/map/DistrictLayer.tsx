import { useTranslation } from 'react-i18next'
import { GeoJSON, Tooltip } from 'react-leaflet'

import { useRadar } from '@/store'

import { DISTRICT_STYLE } from './constants'

/** Raion boundaries with a hover highlight: the hovered raion gets a light
 * grey fill (pure CSS, .district-hit:hover) and its name appears as a bare
 * label pinned to the polygon's center — not a cursor-following tooltip.
 * Leaflet path events bubble to the map by default, so panning and
 * home-placement clicks keep working. */
export default function DistrictLayer() {
  const { i18n } = useTranslation()
  const boundaries = useRadar((s) => s.boundaries)
  const uk = !i18n.language || i18n.language.startsWith('uk')

  return (
    <>
      {boundaries.map((b) => (
        <GeoJSON key={b.id} data={b.geojson} style={{ ...DISTRICT_STYLE, className: 'district-hit' }}>
          {/* Non-sticky center tooltip = static label at the polygon center. */}
          <Tooltip direction="center" className="district-label">
            {uk ? b.name_uk : b.name_en}
          </Tooltip>
        </GeoJSON>
      ))}
    </>
  )
}
