import { useTranslation } from 'react-i18next'

import type { JournalDay } from '@/types'

import { formatDuration } from './journalStats'

interface Props {
  day: JournalDay
  locale: string
}

// Journal days are bucketed by Kyiv local date, so window times must render in
// Kyiv time too — not the browser's zone.
const timeFmt = (locale: string) =>
  new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/Kyiv',
  })

/** The day's air-raid alerts: count + total, then every тривога→відбій interval
 * with the longest one highlighted. */
export default function DayAlerts({ day, locale }: Props) {
  const { t } = useTranslation()
  const fmt = timeFmt(locale)
  // "Longest" only means something against others — never highlight a lone alert.
  const longest = day.alert_windows.length > 1 ? day.longest_alert_seconds : 0

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="panel-title">{t('journal.alerts')}</span>
        {day.alert_count > 0 && (
          <span className="font-mono text-[11px] tabular-nums text-slate-400">
            {day.alert_count}
            <span className="text-slate-600"> · Σ </span>
            {day.alert_incomplete ? '≥ ' : ''}
            {formatDuration(day.alert_seconds)}
          </span>
        )}
      </div>

      {day.alert_count === 0 ? (
        <p className="mt-1.5 text-xs text-slate-500">{t('journal.noAlerts')}</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {day.alert_windows.map((w, i) => {
            const isLongest = longest > 0 && w.seconds === longest
            return (
              <li
                key={i}
                className={`flex items-center justify-between gap-3 rounded-md px-2.5 py-1.5 ${
                  isLongest
                    ? 'border-l-2 border-red-400 bg-red-500/10'
                    : 'border-l-2 border-transparent bg-white/[0.03]'
                }`}
              >
                <span
                  className={`font-mono text-[12px] tabular-nums ${
                    isLongest ? 'text-red-200' : 'text-slate-300'
                  }`}
                >
                  {fmt.format(new Date(w.started_at))}
                  <span className={isLongest ? 'text-red-300/60' : 'text-slate-600'}> – </span>
                  {w.ended_at ? fmt.format(new Date(w.ended_at)) : '…'}
                </span>
                <span className="flex items-center gap-2">
                  {isLongest && (
                    <span className="rounded bg-red-400/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-red-300">
                      {t('journal.longest')}
                    </span>
                  )}
                  <span
                    className={`font-mono text-[11px] tabular-nums ${
                      isLongest ? 'font-semibold text-red-300' : 'text-slate-500'
                    }`}
                  >
                    {w.seconds > 0 ? formatDuration(w.seconds) : '—'}
                  </span>
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
