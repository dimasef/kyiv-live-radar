import { Crosshair, Radiation, Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { MonthSummary as Summary } from './journalStats'
import { formatDuration } from './journalStats'

interface Props {
  summary: Summary
  onJumpToHeaviest: () => void
  locale: string
}

function Tile({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode
  value: string
  label: string
}) {
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

/** Month-at-a-glance strip: attack/target/alert totals plus a link that jumps
 * the selection to the month's heaviest day. */
export default function MonthSummary({ summary, onJumpToHeaviest, locale }: Props) {
  const { t } = useTranslation()
  if (summary.activeDays === 0) return null

  const heaviestLabel = summary.heaviestDate
    ? new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(
        new Date(`${summary.heaviestDate}T00:00:00`),
      )
    : null

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <Tile icon={<Radiation size={15} />} value={String(summary.attacks)} label={t('journal.attacks')} />
        <Tile icon={<Crosshair size={15} />} value={String(summary.targets)} label={t('journal.targets')} />
        <Tile
          icon={<Siren size={15} />}
          value={`${summary.alertIncomplete ? '≥ ' : ''}${formatDuration(summary.alertSeconds)}`}
          label={t('journal.alerts')}
        />
      </div>
      {heaviestLabel && (
        <button onClick={onJumpToHeaviest} className="btn text-[11px]">
          {t('journal.heaviestDay')}
          <span className="ml-1.5 font-mono text-red-400">{heaviestLabel}</span>
        </button>
      )}
    </div>
  )
}
