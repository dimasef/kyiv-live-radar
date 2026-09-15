import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import RouteLink from '@/components/common/RouteLink'
import { isoDayLabel } from '@/lib/kyivTime'
import { journalDayPath } from '@/router'

import { neighbourDays } from './journalStats'

/** Links to the days either side of the one being read.
 *
 * Two jobs. For a reader, "that raid" is rarely one night — the night before is
 * the obvious next question, and getting to it through the calendar grid is a
 * hunt. For a crawler, these are the only links between day pages that do not
 * depend on the heatmap having rendered.
 *
 * Only days with something ON them, and only within the month on screen: an
 * empty day has no page worth publishing (it is not in the sitemap either), and
 * inventing links to a run of them is how a site grows thin pages. Crossing a
 * month is left to the calendar right above, which is what it is for.
 */
export default function DayNav({
  date,
  activeDates,
}: {
  date: string
  /** Every day of the loaded month worth linking to, oldest first. */
  activeDates: string[]
}) {
  const { t, i18n } = useTranslation()
  const { prev, next } = neighbourDays(date, activeDates)
  if (!prev && !next) return null

  return (
    <nav className="mt-3 flex items-center justify-between gap-2 text-xs" aria-label={t('journal.title')}>
      {prev ? (
        <RouteLink
          to={journalDayPath(prev)}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-phosphor-soft"
        >
          <ChevronLeft size={14} className="flex-none" />
          {isoDayLabel(prev, i18n.language)}
        </RouteLink>
      ) : (
        <span />
      )}
      {next && (
        <RouteLink
          to={journalDayPath(next)}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-phosphor-soft"
        >
          {isoDayLabel(next, i18n.language)}
          <ChevronRight size={14} className="flex-none" />
        </RouteLink>
      )}
    </nav>
  )
}
