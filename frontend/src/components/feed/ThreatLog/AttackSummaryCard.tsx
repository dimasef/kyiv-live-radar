import { Swords } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { INCIDENT_SEVERITY_COLOR } from '@/theme'
import type { Incident } from '@/types'

import { DevId, EventTime } from './badges'

function durationLabel(startedAt: string, endedAt: string): string {
  const mins = Math.max(1, Math.round((new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 60000))
  if (mins < 60) return `${mins} хв`
  const h = Math.floor(mins / 60)
  return `${h} год ${mins % 60} хв`
}

/** A retrospective rollup rendered at an attack's ended_at: how long it ran,
 * its classification, and its counts — the "one attack, summarized" card that
 * closes an incident's story in the feed. */
export default function AttackSummaryCard({ incident }: { incident: Incident }) {
  const { t } = useTranslation()
  const color =
    incident.target_type === 'ballistic'
      ? INCIDENT_SEVERITY_COLOR.ballistic
      : INCIDENT_SEVERITY_COLOR.other
  const label = t(`attack.classification.${incident.classification}`, incident.classification)
  const stats = [
    incident.track_count > 0 && `${incident.track_count} ${t('incident.targets')}`,
    incident.impact_count > 0 && `${incident.impact_count} ${t('incident.impacts')}`,
    incident.district_count > 0 && `${incident.district_count} ${t('incident.districts')}`,
  ].filter(Boolean) as string[]

  return (
    <li
      className="feed-item rounded-lg border px-2.5 py-2 text-xs backdrop-blur-sm"
      style={{
        borderColor: `${color}22`,
        borderLeft: `2px solid ${color}`,
        background: `${color}0d`,
        boxShadow: `inset 2px 0 10px -4px ${color}55`,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className="flex items-center gap-1.5 font-semibold uppercase tracking-wide"
          style={{ color }}
        >
          <Swords size={12} className="flex-none" />
          {t('log.attackEnded')}
          {incident.has_hypersonic && (
            <span className="opacity-70">· {t('attack.hypersonic')}</span>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          <DevId>I{incident.id}</DevId>
          {incident.ended_at && <EventTime iso={incident.ended_at} />}
        </span>
      </div>
      <div className="mt-0.5 leading-snug text-slate-300">
        {label}
        {' · '}
        {t('log.duration')} {durationLabel(incident.started_at, incident.ended_at ?? incident.started_at)}
      </div>
      {(stats.length > 0 || incident.decoy_suspected) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] tabular-nums text-slate-500">
          {stats.map((s) => (
            <span key={s}>{s}</span>
          ))}
          {incident.decoy_suspected && (
            <span className="text-slate-400">{t('attack.decoySuspected')}</span>
          )}
        </div>
      )}
    </li>
  )
}
