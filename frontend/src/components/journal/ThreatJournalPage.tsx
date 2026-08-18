import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { riseDelay } from '@/lib/motion'
import { journalTabFromPath, journalTabPath, navigate, useRoute } from '@/router'

import CalendarTab from './CalendarTab'
import JournalTabs from './JournalTabs'
import StatsTab from './stats/StatsTab'

/** Standalone route (/journal): the history of past aerial-threat activity, as
 * a month calendar (/journal) or as period statistics (/journal/stats). */
export default function ThreatJournalPage() {
  const { t } = useTranslation()
  const tab = journalTabFromPath(useRoute())
  // Set when the statistics tab links to one day: remounting CalendarTab with it
  // as the key opens that month/day without any prop-syncing effect.
  const [dayFromStats, setDayFromStats] = useState<string | null>(null)

  const openDay = (date: string) => {
    setDayFromStats(date)
    navigate(journalTabPath('calendar'))
  }

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div
        className={`mx-auto px-4 py-6 sm:px-6 sm:py-10 ${tab === 'stats' ? 'max-w-2xl' : 'max-w-xl'}`}
      >
        <div className="rise" style={riseDelay(1)}>
          <h1 className="font-display text-lg font-bold tracking-wide text-slate-100">
            {t('journal.title')}
          </h1>
          <p className="mt-1 text-[12px] text-slate-500">
            {tab === 'stats' ? t('journal.stats.subtitle') : t('journal.subtitle')}
          </p>
          <JournalTabs active={tab} />
        </div>

        {tab === 'stats' ? (
          <StatsTab onOpenDay={openDay} />
        ) : (
          <CalendarTab key={dayFromStats ?? 'today'} initialDate={dayFromStats} />
        )}
      </div>
    </div>
  )
}
