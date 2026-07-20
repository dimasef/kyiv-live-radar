import { useTranslation } from 'react-i18next'

import { TYPE_COLORS } from '@/theme'
import type { JournalDay } from '@/types'

import {
  INTENSITY_BG,
  INTENSITY_DARK_TEXT,
  intensityBucket,
  monthGrid,
  weekdayLabels,
} from './journalStats'

interface Props {
  year: number
  month0: number
  daysByDate: Map<string, JournalDay>
  selectedDate: string | null
  onSelect: (date: string) => void
  today: string
  locale: string
}

/** Heavy days radiate — a red halo that intensifies with the bucket. */
const CELL_GLOW: readonly (string | undefined)[] = [
  undefined,
  undefined,
  undefined,
  '0 0 12px -3px rgba(248,113,113,0.5)',
  '0 0 20px -2px rgba(239,68,68,0.85)',
]

/** Month heatmap on the ABSOLUTE intensity scale (journalStats.ts) — a heavy
 * day looks equally alarming in any month. A violet dot flags days that saw
 * ballistics. Today and the selected day get a ring. */
export default function CalendarHeatmap({
  year,
  month0,
  daysByDate,
  selectedDate,
  onSelect,
  today,
  locale,
}: Props) {
  const { t } = useTranslation()
  const cells = monthGrid(year, month0)
  const weekdays = weekdayLabels(locale)

  return (
    <div>
      <div className="mb-2 grid grid-cols-7 gap-1.5">
        {weekdays.map((w, i) => (
          <div
            key={i}
            className="text-center font-mono text-[9px] uppercase tracking-[0.14em] text-slate-600"
          >
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((date, i) => {
          if (!date) return <div key={i} />
          const day = daysByDate.get(date)
          const bucket = day ? intensityBucket(day) : 0
          const isSelected = date === selectedDate
          const isToday = date === today
          const dark = INTENSITY_DARK_TEXT[bucket]
          const hadBallistic = (day?.type_counts.ballistic ?? 0) > 0
          const targets = day ? day.target_count + day.impact_count : 0
          return (
            <button
              key={i}
              onClick={() => onSelect(date)}
              aria-pressed={isSelected}
              className={`relative aspect-square rounded-lg p-1 text-left transition-all duration-200 ease-out hover:-translate-y-0.5 hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-phosphor ${
                isSelected
                  ? 'ring-2 ring-phosphor shadow-[0_0_16px_-4px_rgba(34,211,238,0.6)]'
                  : isToday
                    ? 'ring-1 ring-slate-400/60'
                    : ''
              }`}
              style={{ background: INTENSITY_BG[bucket], boxShadow: CELL_GLOW[bucket] }}
            >
              <span
                className={`font-mono text-[10px] leading-none tabular-nums ${
                  dark ? 'text-ink-950' : bucket > 0 ? 'text-red-200/90' : 'text-slate-500'
                }`}
              >
                {Number(date.slice(8, 10))}
              </span>
              {targets > 0 && (
                <span
                  className={`absolute bottom-1 right-1.5 font-mono text-[11px] font-semibold leading-none tabular-nums ${
                    dark ? 'text-ink-950' : 'text-slate-200'
                  }`}
                >
                  {targets}
                </span>
              )}
              {hadBallistic && (
                <span
                  className="absolute left-1 bottom-1 h-1.5 w-1.5 rounded-full"
                  style={{
                    background: TYPE_COLORS.ballistic,
                    boxShadow: `0 0 5px ${TYPE_COLORS.ballistic}`,
                  }}
                />
              )}
            </button>
          )
        })}
      </div>

      <div className="mt-3.5 flex items-center justify-between text-[10px] text-slate-600">
        <span className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: TYPE_COLORS.ballistic, boxShadow: `0 0 5px ${TYPE_COLORS.ballistic}` }}
          />
          {t('target.ballistic')}
        </span>
        <span className="flex items-center gap-1.5">
          <span>{t('journal.less')}</span>
          {INTENSITY_BG.map((bg, i) => (
            <span key={i} className="h-3 w-3 rounded-[4px]" style={{ background: bg }} />
          ))}
          <span>{t('journal.more')}</span>
        </span>
      </div>
    </div>
  )
}
