import { useTranslation } from 'react-i18next'
import { GeoJSON, Tooltip } from 'react-leaflet'

import { useRadar } from '@/store'
import type { AlertZone } from '@/types'

import { sinceParts, zoneTone } from './alertZones'
import { ZONE_STYLES } from './constants'

/** Official air-raid state of the raions of Київщина and Чернігівщина, from an
 * external provider (see backend feeds/alert_zones.py). Purely contextual: it
 * says where sirens are sounding, never where a target is. Rendered below the
 * Kyiv raion outlines so it reads as background, and only while the operator
 * has the layer switched on — the polygons are fetched lazily on that switch. */
export default function AlertZoneLayer() {
  const zones = useRadar((s) => s.zones)
  const geometry = useRadar((s) => s.zoneGeometry)

  return (
    <>
      {Object.entries(geometry).map(([zoneId, shape]) => {
        const zone = zones[zoneId]
        const tone = zone ? zoneTone(zone) : 'stale'
        return (
          // Keyed by tone: Leaflet's setStyle doesn't re-apply a className or
          // dashArray on an existing path, so a state change needs a fresh
          // mount (same trick as CitywidePulse).
          <GeoJSON
            key={`${zoneId}-${tone}`}
            data={shape.geojson}
            style={{ ...ZONE_STYLES[tone], className: 'zone-hit' }}
          >
            {/* Non-sticky center tooltip = a bare label pinned to the polygon
                center, exactly like DistrictLayer's raion names. */}
            <Tooltip direction="center" className="zone-label">
              <ZoneLabel name={shape.name_uk} zone={zone} />
            </Tooltip>
          </GeoJSON>
        )
      })}
    </>
  )
}

/** The raion's name, plus how long a siren has been up. Split out so the
 * ticking clock re-renders one line of text rather than thirteen polygons.
 *
 * A clear zone shows the name alone — its state is already in the fill, and a
 * «відбій» caption on twelve quiet raions is noise. Only the two states worth
 * reading get a second line. */
function ZoneLabel({ name, zone }: { name: string; zone: AlertZone | undefined }) {
  const { t } = useTranslation()
  const nowMs = useRadar((s) => s.nowMs)
  const skew = useRadar((s) => s.clockSkewMs)

  const since = zone && !zone.stale ? sinceParts(zone.changed_at, nowMs + skew) : null
  const held = since && (since.h ? t('zones.hm', since) : t('zones.m', since))
  const caption = !zone || zone.stale
    ? t('zones.noData')
    : zone.alert
      ? [t('zones.alert'), held].filter(Boolean).join(' · ')
      : null

  return (
    <>
      <span className="zone-label-name">{name}</span>
      {caption && <span className="zone-label-state">{caption}</span>}
    </>
  )
}
