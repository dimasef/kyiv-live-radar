import { useTranslation } from 'react-i18next'

import { aftermathGlyphSvg } from '@/aftermathIcons'
import { AFTERMATH_COLOR } from '@/theme'
import type { AftermathCategory, JournalDay } from '@/types'

/** What the night DID — fires, damage, rescue work, casualties.
 *
 * The journal is the only place these reach a reader who is not a vouched
 * account, and only after the відбій (the server holds today's back while a
 * city alert runs — see domain/journal.py). Counts, never raions: naming the
 * places would rebuild the strike map the aggregation exists instead of.
 *
 * Its own file rather than another block inside DayDetail, which was already at
 * the 120-line mark. `DayAlerts` is the same shape and the same reason.
 */

/** Most consequential first — the reverse of the server's severity order,
 * because a list is read from the top while a marker label is taken from the
 * end (domain/aftermath.py owns the order itself). */
const ORDER: AftermathCategory[] = ['casualties', 'rescue', 'fire', 'damage']

export default function DayAftermath({ day }: { day: JournalDay }) {
  const { t } = useTranslation()
  if (day.aftermath_count === 0) return null

  const rows = ORDER.map((c) => ({ category: c, n: day.aftermath_counts[c] ?? 0 })).filter(
    (r) => r.n > 0,
  )

  return (
    <div className="mt-4 border-t border-white/[0.06] pt-4">
      <div className="flex items-baseline justify-between">
        <span className="panel-title">{t('aftermath.title')}</span>
        {/* Reports, not the sum of the categories below — one report can name
            several, so the two numbers legitimately differ and the label says
            which this is. */}
        <span className="font-mono text-[11px] tabular-nums text-slate-400">
          {t('journal.reports', { count: day.aftermath_count })}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
        {rows.map((r) => (
          <span key={r.category} className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <span
              className="flex-none"
              style={{ color: AFTERMATH_COLOR }}
              dangerouslySetInnerHTML={{
                __html: aftermathGlyphSvg(r.category, { size: 13 }),
              }}
            />
            {t(`aftermath.category.${r.category}`, r.category)}
            <span className="font-mono tabular-nums text-slate-200">{r.n}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
