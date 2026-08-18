import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { StatsDay } from '@/types'

import { INTENSITY_BG, intensityBucket, intensityScore } from '../journalStats'
import { formatHours } from './statsMath'

interface Props {
  days: StatsDay[]
  locale: string
  onOpenDay: (date: string) => void
  limit?: number
}

/** The period's worst nights, ranked by the same intensity weighting the
 * calendar colors its cells with. Each row opens that day in the calendar tab. */
export default function HeaviestDays({ days, locale, onOpenDay, limit = 5 }: Props) {
  const { t } = useTranslation()
  const top = [...days]
    .map((d) => ({ day: d, score: intensityScore(d) }))
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
  if (!top.length) return null

  const fmt = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', weekday: 'short' })

  return (
    <div>
      <div className="panel-title mb-2">{t('journal.stats.heaviestDays')}</div>
      <ul className="flex flex-col">
        {top.map(({ day }) => (
          <li key={day.date}>
            <button
              onClick={() => onOpenDay(day.date)}
              className="flex w-full items-center gap-3 border-t border-white/[0.05] py-2 text-left transition-colors hover:bg-white/[0.02]"
            >
              <span
                // Same intensity ramp the calendar cells use, so a row's colour
                // means exactly what that day's cell means.
                className="h-2.5 w-2.5 flex-none rounded-sm"
                style={{ background: INTENSITY_BG[intensityBucket(day)] }}
              />
              <span className="w-24 flex-none text-[11px] capitalize text-slate-300">
                {fmt.format(new Date(`${day.date}T00:00:00`))}
              </span>
              <span className="flex-1 font-mono text-[11px] tabular-nums text-slate-500">
                {t('journal.stats.dayLine', {
                  targets: day.target_count + day.impact_count,
                  alert: formatHours(day.alert_seconds),
                })}
              </span>
              <ChevronRight size={14} className="flex-none text-slate-600" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
