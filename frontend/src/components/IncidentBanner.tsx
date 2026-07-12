import { Crosshair, Flame, Ghost, MapPin, Siren } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../store'
import type { Incident } from '../types'

const SEVERITY: Record<string, number> = {
  ballistic: 4,
  missile: 3,
  jet_drone: 2,
  shahed: 1,
  unknown: 0,
}

/** The single most-severe notable incident to headline, or null if none —
 * shared so other top-center overlays (the inspect badge) can dodge the
 * banner. `notable` itself is computed server-side (see backend
 * serialize.py::_is_notable) — the single source of truth. */
export function notableIncident(incidents: Incident[]): Incident | null {
  const notable = incidents.filter((i) => i.notable)
  if (notable.length === 0) return null
  return [...notable].sort(
    (a, b) => (SEVERITY[b.target_type] ?? 0) - (SEVERITY[a.target_type] ?? 0),
  )[0]
}

/** A summary strip over the map for the current attack ("one alert = one
 * incident"): its dominant weapon type and how many targets / impacts /
 * districts it spans. Subsumes the city-wide alert (a city alert is a member). */
export default function IncidentBanner() {
  const { t } = useTranslation()
  const incidents = useRadar((s) => s.incidents)

  const inc = notableIncident(incidents)
  if (!inc) return null

  const color = inc.target_type === 'ballistic' ? '#ef4444' : '#f97316'

  return (
    <div role="alert" className="incident-banner pointer-events-none flex justify-center">
      <div
        className="flex items-center gap-2.5 rounded-full border px-4 py-2 text-[13px] font-semibold backdrop-blur-md"
        style={
          {
            color,
            borderColor: `${color}66`,
            background: `${color}1f`,
            boxShadow: `0 0 22px -4px ${color}99`,
          } as CSSProperties
        }
      >
        <Siren size={16} className="flex-none animate-pulse" />
        <span className="uppercase tracking-wide">
          {t(`attack.classification.${inc.classification}`)}
          {inc.has_hypersonic && inc.classification === 'ballistic'
            ? ` (${t('attack.hypersonic')})`
            : ''}
        </span>
        {inc.decoy_suspected && (
          <span className="flex-none opacity-80" title={t('attack.decoySuspected')}>
            <Ghost size={13} aria-label={t('attack.decoySuspected')} />
          </span>
        )}
        <span className="flex items-center gap-2 font-mono text-[12px] font-medium tabular-nums opacity-90">
          {inc.track_count > 0 && (
            <span className="flex items-center gap-1" title={t('incident.targets')}>
              <Crosshair size={12} className="flex-none" />
              {inc.track_count}
            </span>
          )}
          {inc.impact_count > 0 && (
            <span className="flex items-center gap-1" title={t('incident.impacts')}>
              <Flame size={12} className="flex-none" />
              {inc.impact_count}
            </span>
          )}
          {inc.district_count > 0 && (
            <span className="flex items-center gap-1" title={t('incident.districts')}>
              <MapPin size={12} className="flex-none" />
              {inc.district_count}
            </span>
          )}
        </span>
      </div>
    </div>
  )
}
