import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchJournal } from '@/api'
import { riseDelay } from '@/lib/motion'
import type { JournalDay } from '@/types'

import CalendarHeatmap from './CalendarHeatmap'
import DayDetail from './DayDetail'
import MonthSummary from './MonthSummary'
import { hasActivity, monthLabel, monthRange, monthSummary, todayISO } from './journalStats'
import { useDistrictNames } from './useDistrictNames'

/** Pick a sensible day to open the detail on after a month loads: today if it's
 * an active day in view, else the most recent active day, else today/last. */
function defaultSelection(days: JournalDay[], preferred: string | null): string | null {
  if (preferred && days.some((d) => d.date === preferred)) return preferred
  const today = todayISO()
  const active = days.filter(hasActivity)
  if (active.some((d) => d.date === today)) return today
  if (active.length) return active[active.length - 1].date
  if (days.some((d) => d.date === today)) return today
  return days[days.length - 1]?.date ?? null
}

/** The month calendar of past aerial-threat activity: an intensity heatmap plus
 * the selected day's breakdown. `initialDate` opens on that day's month (the
 * statistics tab links here); the page remounts this on change, so there is no
 * prop-syncing effect. */
export default function CalendarTab({ initialDate = null }: { initialDate?: string | null }) {
  const { t, i18n } = useTranslation()
  const locale = i18n.language?.startsWith('en') ? 'en-GB' : 'uk-UA'
  const now = new Date()
  const opening = initialDate ? new Date(`${initialDate}T00:00:00`) : now
  const [year, setYear] = useState(opening.getFullYear())
  const [month0, setMonth0] = useState(opening.getMonth())
  const [days, setDays] = useState<JournalDay[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const districtName = useDistrictNames()

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    const { from, to } = monthRange(year, month0)
    fetchJournal(from, to)
      .then((j) => {
        if (cancelled) return
        setDays(j.days)
        setSelectedDate(defaultSelection(j.days, initialDate))
        setPhase('ready')
      })
      .catch(() => {
        if (cancelled) return
        setDays([])
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
    // initialDate never changes within a mount — the page remounts to change it.
  }, [year, month0, initialDate])

  const daysByDate = useMemo(() => new Map(days.map((d) => [d.date, d])), [days])
  const summary = useMemo(() => monthSummary(days), [days])
  const selected = selectedDate ? (daysByDate.get(selectedDate) ?? null) : null

  const shiftMonth = (delta: number) => {
    const d = new Date(year, month0 + delta, 1)
    setYear(d.getFullYear())
    setMonth0(d.getMonth())
  }
  const atCurrentMonth =
    year > now.getFullYear() || (year === now.getFullYear() && month0 >= now.getMonth())

  return (
    <>
      <div className="rise panel mt-4 p-4 sm:p-5" style={riseDelay(2)}>
        <div className="mb-4 flex items-center justify-between">
          <button
            onClick={() => shiftMonth(-1)}
            className="btn !p-1.5"
            aria-label={t('journal.prevMonth')}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="font-display text-[13px] font-semibold capitalize tracking-wide text-slate-200">
            {monthLabel(year, month0, locale)}
          </span>
          <button
            onClick={() => shiftMonth(1)}
            disabled={atCurrentMonth}
            className="btn !p-1.5 disabled:pointer-events-none disabled:opacity-30"
            aria-label={t('journal.nextMonth')}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {phase === 'error' ? (
          <div className="py-10 text-center text-xs text-slate-500">{t('journal.loadError')}</div>
        ) : phase === 'loading' ? (
          <div className="grid animate-pulse grid-cols-7 gap-1.5">
            {Array.from({ length: 35 }, (_, i) => (
              <div key={i} className="aspect-square rounded-lg bg-white/[0.03]" />
            ))}
          </div>
        ) : (
          <>
            {summary.activeDays > 0 && (
              <div className="mb-4 border-b border-white/[0.06] pb-4">
                <MonthSummary
                  summary={summary}
                  onJumpToHeaviest={() =>
                    summary.heaviestDate && setSelectedDate(summary.heaviestDate)
                  }
                  locale={locale}
                />
              </div>
            )}
            <CalendarHeatmap
              year={year}
              month0={month0}
              daysByDate={daysByDate}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
              today={todayISO()}
              locale={locale}
            />
          </>
        )}
      </div>

      {phase === 'ready' && (
        <div className="rise panel mt-4 p-4 sm:p-5" style={riseDelay(3)}>
          <DayDetail day={selected} districtName={districtName} locale={locale} />
        </div>
      )}
    </>
  )
}
