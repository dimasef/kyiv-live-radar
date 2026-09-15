import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isoDayLabel } from '@/lib/kyivTime'
import { riseDelay } from '@/lib/motion'
import { journalDateFromPath, journalDayPath, journalTabFromPath, navigate, useRoute } from '@/router'
import { useRadar } from '@/store'

import CalendarTab from './CalendarTab'
import { foreignJournalRegion } from './journalRegion'
import JournalRegionGate from './JournalRegionGate'
import JournalTabs from './JournalTabs'
import StatsTab from './stats/StatsTab'

/** Standalone route (/journal): the history of past aerial-threat activity, as
 * a month calendar (/journal) or as period statistics (/journal/stats). */
export default function ThreatJournalPage() {
  const { t, i18n } = useTranslation()
  const route = useRoute()
  const tab = journalTabFromPath(route)
  const day = journalDateFromPath(route)
  const regions = useRadar((s) => s.regions)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const ensureRegions = useRadar((s) => s.ensureRegions)
  // The journal is a bookmarkable route that never bootstraps the map, so on a
  // direct load the catalogue is empty — and an empty catalogue is exactly when
  // the gate below silently decides there is nothing to warn about. Idempotent
  // and guarded in the store (same call as SourcesPanel, for the same reason).
  ensureRegions()
  // Answered once per visit rather than remembered: switching tabs keeps this
  // component mounted, and the journal is a deliberate destination, not
  // somewhere you pass through. The subtitle keeps saying whose data it is
  // afterwards — that, not the gate, is what stops it being misread later.
  const [acknowledged, setAcknowledged] = useState(false)

  const foreignRegion = foreignJournalRegion(regions, chosenRegion)
  const gated = foreignRegion !== null && !acknowledged

  const openDay = (date: string) => navigate(journalDayPath(date))

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="page-col px-4 py-6 sm:px-6 sm:py-10">
        <div className="rise" style={riseDelay(1)}>
          {/* On a day route the date IS the heading. Without this all 63 day
              pages carried the same <h1>«Журнал»</h1> — the heaviest on-page
              signal, identical across the very pages that exist to differ. */}
          <h1 className="font-display text-lg font-bold tracking-wide text-slate-100">
            {day ? isoDayLabel(day, i18n.language) : t('journal.title')}
          </h1>
          <p className="mt-1 text-[12px] text-slate-500">
            {foreignRegion !== null
              ? t('journal.regionGate.subtitle', { region: foreignRegion })
              : tab === 'stats'
                ? t('journal.stats.subtitle')
                : t('journal.subtitle')}
          </p>
          {!gated && <JournalTabs active={tab} />}
        </div>

        {gated ? (
          <JournalRegionGate
            homeName={foreignRegion}
            onProceed={() => setAcknowledged(true)}
          />
        ) : tab === 'stats' ? (
          <StatsTab onOpenDay={openDay} />
        ) : (
          // Keyed by MONTH, not by day: picking another day in the month on
          // screen only changes the URL, while a link into a different month
          // (from the statistics tab, or from outside) remounts and fetches it.
          // Keying by day would refetch the month on every cell click.
          <CalendarTab key={day?.slice(0, 7) ?? 'today'} date={day} onSelectDay={openDay} />
        )}
      </div>
    </div>
  )
}
