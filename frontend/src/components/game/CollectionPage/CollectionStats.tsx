import { rarityBreakdown, totalCopies } from '@/lib/cards'

import type { Tab } from './RarityTabs'

/** Cards on hand in whatever the filter is showing — copies, duplicates and
 * all, against the filter pills' distinct-card counts. It follows the selected
 * tab, so «Звичайні 15/15» reads as 15 distinct commons out of 226 actual
 * cards. Deliberately not a button: it counts, it doesn't filter. */
export default function CollectionStats({
  counts,
  tab,
}: {
  counts: Map<number, number>
  tab: Tab
}) {
  const copies = tab === 'all' ? totalCopies(counts) : rarityBreakdown(counts)[tab].copies

  return (
    // Opaque and slightly lifted off the rail; the rail's own mask is what
    // actually dissolves a filter swiped past it.
    <span className="inline-flex flex-none items-center gap-2 whitespace-nowrap rounded-full border border-white/[0.09] bg-ink-950 px-3.5 py-2 font-mono text-[11.5px] tracking-[0.08em] text-slate-500 shadow-[-8px_0_14px_-6px_#05080d]">
      УСЬОГО <span className="text-slate-100">{copies}</span>
    </span>
  )
}
