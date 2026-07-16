import { GeoJSON } from 'react-leaflet'

import { useRadar } from '../../store'
import { TYPE_COLORS } from '../../theme'

/** Raions under an active attack get their boundary filled in the attack's type
 * colour — turning the inert district layer into a live "where the attack is"
 * heat. When the operator focuses one incident (tapping an "Атака #N" chip in
 * the feed), only that incident's raions light up. */
export default function IncidentHighlight() {
  const incidents = useRadar((s) => s.incidents)
  const focusedId = useRadar((s) => s.focusedIncidentId)
  const boundaries = useRadar((s) => s.boundaries)

  if (boundaries.length === 0) return null
  const active = incidents.filter((i) => i.status === 'active')
  const source = focusedId != null ? active.filter((i) => i.id === focusedId) : active
  if (source.length === 0) return null

  // district_id -> colour of the (most recent) attack touching it.
  const colorByDistrict = new Map<number, string>()
  for (const inc of source) {
    const color = TYPE_COLORS[inc.target_type] ?? TYPE_COLORS.unknown
    for (const did of inc.district_ids) colorByDistrict.set(did, color)
  }

  return (
    <>
      {boundaries
        .filter((b) => colorByDistrict.has(b.id))
        .map((b) => {
          const color = colorByDistrict.get(b.id)!
          return (
            <GeoJSON
              key={`incident-${b.id}-${color}-${focusedId ?? 'all'}`}
              data={b.geojson}
              interactive={false}
              style={{ color, weight: 1.5, opacity: 0.7, fillColor: color, fillOpacity: 0.18 }}
            />
          )
        })}
    </>
  )
}
