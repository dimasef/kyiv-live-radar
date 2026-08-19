import { ChevronRight } from 'lucide-react'

import type { Collection } from '@/api'
import { CARDS, RARITIES, RARITY_STYLE, collectionCounts, rarityBreakdown } from '@/lib/cards'
import { collectionPath, navigate } from '@/router'

/** Collection progress + a per-rarity breakdown; the whole card links through to
 * the full collection. Shown for your own account and, on a contact's profile,
 * for theirs — `userId` picks which collection the link opens. */
export default function CollectionSummaryCard({
  collection,
  userId,
}: {
  collection: Collection | null
  /** Omitted for your own collection. */
  userId?: number
}) {
  const counts = collectionCounts(collection?.cards)
  const breakdown = rarityBreakdown(counts)
  const total = collection?.card_count ?? CARDS.length
  const pct = total ? Math.round((counts.size / total) * 100) : 0

  return (
    <button
      onClick={() => navigate(collectionPath(userId))}
      className="panel w-full p-4 text-left transition-colors hover:border-phosphor/30"
    >
      <div className="flex items-center justify-between">
        <span className="panel-title">Колекція карток</span>
        <ChevronRight size={16} className="text-slate-500" />
      </div>
      <p className="mt-2 font-mono text-xs text-slate-500">
        Зібрано <span className="text-phosphor-soft">{counts.size}</span> / {total}
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full bg-phosphor/70" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {RARITIES.map((r) => (
          <span key={r} className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <i className="h-[6px] w-[6px] rounded-full" style={{ background: RARITY_STYLE[r].rc }} />
            {RARITY_STYLE[r].label}
            <span className="font-mono text-slate-500">
              {breakdown[r].have}/{breakdown[r].total}
            </span>
          </span>
        ))}
      </div>
    </button>
  )
}
