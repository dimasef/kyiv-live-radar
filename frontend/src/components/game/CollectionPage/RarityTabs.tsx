import { RARITIES, RARITY_STYLE, rarityBreakdown, type Rarity } from '@/lib/cards'

export type Tab = 'all' | Rarity

/** Rarity filter tabs, each with an owned/total badge; the "Усі" tab shows the
 * overall total. */
export default function RarityTabs({
  tab,
  onSelect,
  counts,
  total,
}: {
  tab: Tab
  onSelect: (tab: Tab) => void
  counts: Map<number, number>
  total: number
}) {
  const breakdown = rarityBreakdown(counts)
  return (
    <div className="mb-4 flex flex-wrap gap-1.5">
      <TabChip label="Усі" active={tab === 'all'} onClick={() => onSelect('all')} owned={counts.size} total={total} />
      {RARITIES.map((r) => (
        <TabChip
          key={r}
          label={RARITY_STYLE[r].plural}
          color={RARITY_STYLE[r].rc}
          active={tab === r}
          onClick={() => onSelect(r)}
          owned={breakdown[r].have}
          total={breakdown[r].total}
        />
      ))}
    </div>
  )
}

function TabChip({
  label,
  color,
  active,
  onClick,
  owned,
  total,
}: {
  label: string
  color?: string
  active: boolean
  onClick: () => void
  owned: number
  total: number
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors ${
        active
          ? 'border-white/20 bg-white/[0.08] text-slate-100'
          : 'border-white/[0.07] bg-white/[0.02] text-slate-400 hover:text-slate-200'
      }`}
    >
      {color && <i className="h-[6px] w-[6px] rounded-full" style={{ background: color }} />}
      {label}
      <span className="font-mono text-[10px] text-slate-500">
        {owned}/{total}
      </span>
    </button>
  )
}
