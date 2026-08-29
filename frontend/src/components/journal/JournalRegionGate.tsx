import { MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { MAP_PATH, navigate } from '@/router'

/** Shown before the journal to a reader who follows a different oblast than the
 * one the journal is about.
 *
 * The journal aggregates server-side and is pinned to the deployment's home
 * region (backend api/journal_window.py) — northern tracks are watched to see
 * what is coming, not counted as nights that city lived through. For a reader
 * following Сумщина that makes every number on the page someone else's: their
 * own oblast's targets are not in it, and its attack and alert figures come
 * from a city they are not in.
 *
 * A gate rather than a footnote, because the failure is silent: the page looks
 * exactly the same either way, and a heat map of Kyiv raions reads as "my area"
 * to anyone not already suspicious. The choice is deliberately two-sided —
 * these ARE real numbers and worth reading if you want them, so the answer is
 * "show me anyway" or "take me back", not a dismissible warning.
 */
export default function JournalRegionGate({
  homeName,
  onProceed,
}: {
  homeName: string
  onProceed: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="panel mt-6 rounded-xl p-4">
      <div className="flex items-start gap-2.5">
        <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
        <div>
          <h2 className="font-display text-sm font-bold tracking-wide text-slate-100">
            {t('journal.regionGate.title', { region: homeName })}
          </h2>
          <p className="mt-1.5 text-[12px] leading-relaxed text-slate-400">
            {t('journal.regionGate.body', { region: homeName })}
          </p>
        </div>
      </div>
      <div className="mt-3.5 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onProceed}
          className="rounded-lg border border-white/15 px-3 py-1.5 text-[12px] font-semibold text-slate-100 transition-colors hover:bg-white/10"
        >
          {t('journal.regionGate.show', { region: homeName })}
        </button>
        <button
          type="button"
          onClick={() => navigate(MAP_PATH)}
          className="rounded-lg bg-phosphor/20 px-3 py-1.5 text-[12px] font-semibold text-phosphor-soft transition-colors hover:bg-phosphor/30"
        >
          {t('journal.regionGate.toMap')}
        </button>
      </div>
    </div>
  )
}
