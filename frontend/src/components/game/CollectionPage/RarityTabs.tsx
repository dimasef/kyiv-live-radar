import { RARITY_STYLE, RARITIES, rarityBreakdown, type Rarity } from '@/lib/cards'

export type Tab = 'all' | Rarity

const FADE_RIGHT = 'linear-gradient(to right, #000 calc(100% - 32px), transparent)'

/** Rarity filter pills, in the mock's pill styling, each carrying how much of
 * that rarity is unlocked — distinct cards, not copies; the copies of whatever
 * is selected are counted by the chip beside them (CollectionStats). The
 * unselected pills are dimmed rather than recoloured, so the rarity accent stays
 * the thing that identifies a pill. */
export default function RarityTabs({
  tab,
  onSelect,
  counts,
  total,
}: {
  tab: Tab
  onSelect: (tab: Tab) => void
  counts: Map<number, number>
  /** Deck size, for the «Усі» pill. */
  total: number
}) {
  const breakdown = rarityBreakdown(counts)
  return (
    // One rail, never wrapping: on a phone the pills run off the right edge and
    // are swiped through. The mask fades a leaving pill out instead of letting
    // the scroll box slice it down the middle — it masks the pill itself, so it
    // works whatever is behind the rail. `pr-8` matches the fade, so the last
    // pill parks clear of it at the end of the swipe rather than half-ghosted;
    // `-my-1 py-1` keeps the active dot's glow out of the overflow clip.
    <div
      className="scroll-none -my-1 flex gap-2 overflow-x-auto py-1 pr-8"
      style={{ maskImage: FADE_RIGHT, WebkitMaskImage: FADE_RIGHT }}
    >
      <Pill
        label="Усі"
        color="#67e8f9"
        dot={false}
        have={counts.size}
        total={total}
        active={tab === 'all'}
        onClick={() => onSelect('all')}
      />
      {RARITIES.map((r) => (
        <Pill
          key={r}
          label={RARITY_STYLE[r].plural}
          color={RARITY_STYLE[r].rc}
          have={breakdown[r].have}
          total={breakdown[r].total}
          active={tab === r}
          onClick={() => onSelect(r)}
        />
      ))}
    </div>
  )
}

function Pill({
  label,
  color,
  dot = true,
  have,
  total,
  active,
  onClick,
}: {
  label: string
  color: string
  dot?: boolean
  have: number
  total: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex flex-none items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 font-mono text-[11.5px] tracking-[0.08em] transition-opacity ${
        active ? 'opacity-100' : 'opacity-50 hover:opacity-80'
      }`}
      style={{
        borderColor: hexAlpha(color, active ? 0.55 : 0.28),
        background: hexAlpha(color, active ? 0.14 : 0.05),
        color,
      }}
    >
      {dot && (
        <i
          className="h-2 w-2 rounded-full"
          style={{ background: color, boxShadow: active ? `0 0 7px ${color}` : 'none' }}
        />
      )}
      {label.toUpperCase()}
      <span className="text-slate-200">
        {have}/{total}
      </span>
    </button>
  )
}

function hexAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.replace('#', ''), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
