import { Check } from 'lucide-react'

import { RARITY_RGB, RARITY_STYLE, type Rarity } from '@/lib/cards'

/** The mark of a fully collected rarity: a lit check in a ring, the words, and
 * the count — a small trophy in the section's corner rather than a chip. */
export default function CompleteSeal({
  rarity,
  total,
  copies,
}: {
  rarity: Rarity
  total: number
  copies: string
}) {
  const rc = RARITY_STYLE[rarity].rc
  const rgb = RARITY_RGB[rarity]
  return (
    <div
      className="flex items-center gap-2.5 rounded-xl border py-2 pl-2.5 pr-3"
      style={{
        borderColor: `rgba(${rgb}, 0.55)`,
        background: `linear-gradient(135deg, rgba(${rgb}, 0.2), rgba(${rgb}, 0.06))`,
        boxShadow: `0 0 28px -8px rgba(${rgb}, 0.7), inset 0 0 0 1px rgba(${rgb}, 0.12)`,
      }}
    >
      <span
        className="flex h-7 w-7 flex-none items-center justify-center rounded-full border"
        style={{ borderColor: rc, color: rc, boxShadow: `0 0 12px rgba(${rgb}, 0.7)` }}
      >
        <Check size={14} strokeWidth={3} />
      </span>
      <div className="text-left leading-tight">
        <div className="whitespace-nowrap font-display text-[12px] font-bold" style={{ color: rc }}>
          Зібрано повністю
        </div>
        <div className="mt-0.5 whitespace-nowrap font-mono text-[10px] tracking-[0.16em] text-slate-400">
          {total}/{total} · {copies}
        </div>
      </div>
    </div>
  )
}
