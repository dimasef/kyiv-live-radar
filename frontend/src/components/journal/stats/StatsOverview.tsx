import { Crosshair, Radiation, Radio, Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { JournalStats } from '@/types'

import { alertTimeShare, formatHours, formatPercent } from './statsMath'

function Tile({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-phosphor-soft/70">{icon}</span>
      <span className="flex flex-col">
        <span className="font-mono text-[15px] font-semibold leading-tight tabular-nums text-slate-100">
          {value}
        </span>
        <span className="text-[9px] uppercase tracking-[0.12em] text-slate-500">{label}</span>
      </span>
    </div>
  )
}

/** The period's headline: total time under alert (the one number this page leads
 * with) plus the counting tiles. */
export default function StatsOverview({ stats }: { stats: JournalStats }) {
  const { t } = useTranslation()
  const totals = stats.totals
  const share = alertTimeShare(totals.alert_seconds, stats.alert_days_observed)
  const lowerBound = totals.alert_incomplete ? '≥ ' : ''

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-4xl font-semibold leading-none text-slate-100">
          {lowerBound}
          {formatHours(totals.alert_seconds)}
        </span>
        <span className="text-[11px] text-slate-500">
          {t('journal.stats.underAlert', { percent: formatPercent(share, 1) })}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4">
        <Tile
          icon={<Siren size={15} />}
          value={String(totals.alerts)}
          label={t('journal.stats.alertCount')}
        />
        <Tile
          icon={<Radiation size={15} />}
          value={String(totals.attacks)}
          label={t('journal.attacks')}
        />
        <Tile
          icon={<Crosshair size={15} />}
          value={String(totals.targets + totals.impacts)}
          label={t('journal.targets')}
        />
        <Tile
          icon={<Radio size={15} />}
          value={`${totals.active_days}/${stats.days_observed}`}
          label={t('journal.stats.activeDays')}
        />
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
        {t('journal.stats.longestAlert')}{' '}
        <span className="font-mono tabular-nums text-slate-300">
          {formatHours(totals.longest_alert_seconds)}
        </span>
        {totals.quiet_streak_days > 0 && (
          <>
            {' · '}
            {t('journal.stats.quietStreak', { n: totals.quiet_streak_days })}
          </>
        )}
      </p>
    </div>
  )
}
