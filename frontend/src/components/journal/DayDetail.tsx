import { useTranslation } from 'react-i18next'

import { TYPE_COLORS } from '@/theme'
import type { JournalDay } from '@/types'

import DayAlerts from './DayAlerts'
import { hasActivity, typeSegments } from './journalStats'

interface Props {
  day: JournalDay | null
  districtName: (id: number) => string
  locale: string
}

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-mono text-2xl font-semibold tabular-nums text-slate-100">{value}</span>
      <span className="mt-0.5 text-[9px] uppercase tracking-[0.12em] text-slate-500">{label}</span>
    </div>
  )
}

/** Breakdown panel for the selected day: attacks/targets, a type-mix bar,
 * alert duration and the most-active districts (backend orders them by event
 * count, so the head of the list is the day's hottest area). */
export default function DayDetail({ day, districtName, locale }: Props) {
  const { t } = useTranslation()

  if (!day) {
    return <div className="py-8 text-center text-xs text-slate-500">{t('journal.pickDay')}</div>
  }

  const heading = new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date(`${day.date}T00:00:00`))

  const segments = typeSegments(day)
  const segTotal = segments.reduce((n, s) => n + s.count, 0)

  return (
    // Re-keyed by date so switching days replays the entrance — the panel
    // visibly responds to the selection instead of mutating in place.
    <div key={day.date} className="rise">
      <h2 className="font-display text-[13px] font-bold capitalize tracking-wide text-slate-100">
        {heading}
      </h2>

      {!hasActivity(day) ? (
        <p className="mt-3 text-xs text-slate-500">{t('journal.quietDay')}</p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Stat value={day.attack_count} label={t('journal.attacks')} />
            <Stat value={day.target_count + day.impact_count} label={t('journal.targets')} />
          </div>

          {segTotal > 0 && (
            <div className="mt-5">
              <div className="panel-title mb-2">{t('journal.byType')}</div>
              <div className="flex h-2 gap-px overflow-hidden rounded-full">
                {segments.map((s) => (
                  <div
                    key={s.type}
                    className="transition-all duration-500 ease-out"
                    style={{
                      width: `${(s.count / segTotal) * 100}%`,
                      background: TYPE_COLORS[s.type],
                      boxShadow: `0 0 8px -2px ${TYPE_COLORS[s.type]}`,
                    }}
                  />
                ))}
              </div>
              <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
                {segments.map((s) => (
                  <span key={s.type} className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    <span
                      className="h-2 w-2 flex-none rounded-sm"
                      style={{ background: TYPE_COLORS[s.type] }}
                    />
                    {t(`target.${s.type}`)}
                    <span className="font-mono tabular-nums text-slate-200">{s.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5 border-t border-white/[0.06] pt-4">
            <DayAlerts day={day} locale={locale} />
          </div>

          {day.district_count > 0 && (
            <div className="mt-4 border-t border-white/[0.06] pt-4">
              <div className="flex items-baseline justify-between">
                <span className="panel-title">{t('journal.districts')}</span>
                <span className="font-mono text-[11px] tabular-nums text-slate-400">
                  {day.district_count}
                </span>
              </div>
              <div
                className="mt-1.5 text-[11px] leading-relaxed text-slate-500"
                title={day.district_ids.map(districtName).join(', ')}
              >
                {day.district_ids.slice(0, 6).map(districtName).join(', ')}
                {day.district_count > 6 ? '…' : ''}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
