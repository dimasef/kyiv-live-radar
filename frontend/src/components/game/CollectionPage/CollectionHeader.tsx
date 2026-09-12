import { ChevronLeft, Info } from 'lucide-react'

import CollectionStats from './CollectionStats'
import RarityTabs, { type Tab } from './RarityTabs'

/** Title, totals and rarity filters, riding along while the grid scrolls under
 * them. Solid ink, not a blur: a backdrop-filter over a long scrolling grid is
 * the one effect this page cannot afford (see the map render budget).
 *
 * The page owns no top padding — this block does (`pt-6`). A sticky element is
 * held inside its scroll container's PADDING box, so with `py-6` on the page and
 * `top-0` here the browser pushes this bar 24px below its flow position and it
 * eats the top of the first card row. `-mx-4` still cancels the page's side
 * gutters, so nothing scrolls past it at the edges. */
export default function CollectionHeader({
  ownerName,
  onShowRules,
  tab,
  onSelectTab,
  counts,
  total,
}: {
  /** Whose collection this is, when it isn't yours. */
  ownerName: string | null
  /** Omitted on a friend's collection — the rules are about earning your own. */
  onShowRules?: () => void
  tab: Tab
  onSelectTab: (tab: Tab) => void
  counts: Map<number, number>
  total: number
}) {
  return (
    <div className="sticky top-0 z-20 -mx-4 bg-ink-950 px-4 pb-4 pt-6">
      <header className="mb-4 flex items-start gap-3">
        <button
          onClick={() => window.history.back()}
          aria-label="Назад"
          className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-100"
        >
          <ChevronLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-phosphor-soft">
            UA Live Radar // Колекція
          </span>
          <h1 className="font-display text-xl font-bold text-slate-100">
            {ownerName ? `Картки: ${ownerName}` : 'Мої картки'}
          </h1>
        </div>
        {onShowRules && (
          <button
            onClick={onShowRules}
            aria-label="Як отримати картки"
            className="flex h-10 w-10 flex-none items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-100"
          >
            <Info size={20} />
          </button>
        )}
      </header>

      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <RarityTabs tab={tab} onSelect={onSelectTab} counts={counts} total={total} />
        </div>
        <CollectionStats counts={counts} tab={tab} />
      </div>

      {/* Cards dissolve into the bar instead of being sliced by its edge. */}
      <div className="pointer-events-none absolute inset-x-0 top-full h-4 bg-gradient-to-b from-ink-950 to-transparent" />
    </div>
  )
}
