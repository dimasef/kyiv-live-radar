import { ChevronRight } from 'lucide-react'

import type { Collection } from '@/api'
import {
  CARDS,
  RARITIES,
  RARITY_STYLE,
  collectionCounts,
  rarityBreakdown,
  totalCopies,
} from '@/lib/cards'
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
  // A tier you have nothing from stays unnamed here — the pill would only
  // advertise what you haven't seen yet, and an empty collection shows none.
  const started = RARITIES.filter((r) => breakdown[r].have > 0)

  return (
    <button
      onClick={() => navigate(collectionPath(userId))}
      className="panel w-full p-4 text-left transition-colors hover:border-phosphor/30"
    >
      <div className="flex items-center justify-between">
        <span className="panel-title">Колекція карток</span>
        <ChevronRight size={16} className="text-slate-500" />
      </div>
      <p className="mt-2 font-mono text-sm text-slate-500">
        Зібрано <span className="text-phosphor-soft">{counts.size}</span> / {total}
        {' · Усього '}
        <span className="text-slate-300">{totalCopies(counts)}</span>
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full bg-phosphor/70" style={{ width: `${pct}%` }} />
      </div>
      {/* The same pills as the collection page's filters — this card is that
          page's doorstep, so the two should read as one surface. */}
      <div className="mt-3 flex flex-wrap gap-2 empty:mt-0">
        {started.map((r) => {
          const s = RARITY_STYLE[r]
          return (
            <span
              key={r}
              className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1.5 font-mono text-[11px] tracking-[0.08em]"
              style={{
                borderColor: hexAlpha(s.rc, 0.3),
                background: hexAlpha(s.rc, 0.06),
                color: s.rc,
              }}
            >
              <i className="h-1.5 w-1.5 rounded-full" style={{ background: s.rc }} />
              {s.plural.toUpperCase()}
              <span className="text-slate-200">
                {breakdown[r].have}/{breakdown[r].total}
              </span>
            </span>
          )
        })}
      </div>
    </button>
  )
}

function hexAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.replace('#', ''), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
