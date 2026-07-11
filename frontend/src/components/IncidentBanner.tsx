import { Crosshair, Flame, MapPin, Siren } from 'lucide-react'
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

/** Whether an incident is worth a prominent banner — a coordinated attack, not
 * a single lone drone (which is adequately shown by its map dot alone). */
function isNotable(i: Incident): boolean {
  return (
    i.target_type === 'ballistic' ||
    i.citywide ||
    i.impact_count > 0 ||
    i.track_count + i.impact_count >= 2
  )
}

/** A summary strip over the map for the current attack ("one alert = one
 * incident"): its dominant weapon type and how many targets / impacts /
 * districts it spans. Subsumes the city-wide alert (a city alert is a member). */
export default function IncidentBanner() {
  const { t } = useTranslation()
  const incidents = useRadar((s) => s.incidents)

  const notable = incidents.filter(isNotable)
  if (notable.length === 0) return null
  // Show the most severe ongoing attack.
  const inc = [...notable].sort(
    (a, b) => (SEVERITY[b.target_type] ?? 0) - (SEVERITY[a.target_type] ?? 0),
  )[0]

  const color = inc.target_type === 'ballistic' ? '#ef4444' : '#f97316'

  return (
    <div
      role="alert"
      className="incident-banner pointer-events-none absolute inset-x-0 top-0 z-[1000] flex justify-center px-3 pt-3"
    >
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
          {t(`incident.type.${inc.target_type}`)}
        </span>
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
