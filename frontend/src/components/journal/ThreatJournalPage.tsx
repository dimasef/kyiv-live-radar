import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchDistricts, fetchJournal } from '@/api'
import { riseDelay } from '@/lib/motion'
import { navigate } from '@/router'
import type { JournalDay } from '@/types'

import CalendarHeatmap from './CalendarHeatmap'
import DayDetail from './DayDetail'
import MonthSummary from './MonthSummary'
import { hasActivity, monthLabel, monthRange, monthSummary, todayISO } from './journalStats'

/** Pick a sensible day to open the detail on after a month loads: today if it's
 * an active day in view, else the most recent active day, else today/last. */
function defaultSelection(days: JournalDay[]): string | null {
  const today = todayISO()
  const active = days.filter(hasActivity)
  if (active.some((d) => d.date === today)) return today
  if (active.length) return active[active.length - 1].date
  if (days.some((d) => d.date === today)) return today
  return days[days.length - 1]?.date ?? null
}

/** Standalone route (/journal): a calendar of past aerial-threat activity —
 * per-day attacks/targets/types and alert duration, with an intensity heatmap. */
export default function ThreatJournalPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language?.startsWith('en') ? 'en-GB' : 'uk-UA'
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month0, setMonth0] = useState(now.getMonth())
  const [days, setDays] = useState<JournalDay[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [districts, setDistricts] = useState<Map<number, string>>(new Map())

  useEffect(() => {
    fetchDistricts()
      .then((ds) => setDistricts(new Map(ds.map((d) => [d.id, d.name_uk]))))
      .catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    const { from, to } = monthRange(year, month0)
    fetchJournal(from, to)
      .then((j) => {
        if (cancelled) return
        setDays(j.days)
        setSelectedDate(defaultSelection(j.days))
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
  }, [year, month0])

  const daysByDate = useMemo(() => new Map(days.map((d) => [d.date, d])), [days])
  const summary = useMemo(() => monthSummary(days), [days])
  const selected = selectedDate ? (daysByDate.get(selectedDate) ?? null) : null
  const districtName = (id: number) => districts.get(id) ?? `#${id}`

  const shiftMonth = (delta: number) => {
    const d = new Date(year, month0 + delta, 1)
    setYear(d.getFullYear())
    setMonth0(d.getMonth())
  }
  const atCurrentMonth =
    year > now.getFullYear() || (year === now.getFullYear() && month0 >= now.getMonth())

  return (
    <div className="h-[100dvh] overflow-y-auto overscroll-contain">
      <div className="mx-auto max-w-xl px-4 py-6 sm:px-6 sm:py-10">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault()
            navigate('/')
          }}
          className="rise mb-6 inline-flex items-center gap-2 text-[13px] text-slate-400 transition-colors hover:text-slate-100"
          style={riseDelay(0)}
        >
          <ArrowLeft size={16} />
          {t('journal.back')}
        </a>

        <div className="rise" style={riseDelay(1)}>
          <h1 className="font-display text-lg font-bold tracking-wide text-slate-100">
            {t('journal.title')}
          </h1>
          <p className="mt-1 text-[12px] text-slate-500">{t('journal.subtitle')}</p>
        </div>

        <div className="rise panel mt-6 p-4 sm:p-5" style={riseDelay(2)}>
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
      </div>
    </div>
  )
}
