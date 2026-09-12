import { totalCopies } from '@/lib/cards'

/** Cards on hand across the whole deck — copies, duplicates and all, against
 * the nav pills' distinct-card counts. Deliberately not a button: it counts,
 * it doesn't navigate. */
export default function CollectionStats({ counts }: { counts: Map<number, number> }) {
  return (
    // Opaque and slightly lifted off the rail; the rail's own mask is what
    // actually dissolves a pill swiped past it.
    <span className="inline-flex flex-none items-center gap-2 whitespace-nowrap rounded-full border border-white/[0.09] bg-ink-950 px-3.5 py-2 font-mono text-[11.5px] tracking-[0.08em] text-slate-500 shadow-[-8px_0_14px_-6px_#05080d]">
      УСЬОГО <span className="text-slate-100">{totalCopies(counts)}</span>
    </span>
  )
}
