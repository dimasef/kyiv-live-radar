import { useEffect, useRef } from 'react'

import { RARITY_STYLE, RARITIES, rarityBreakdown, type Rarity } from '@/lib/cards'

const FADE_RIGHT = 'linear-gradient(to right, #000 calc(100% - 32px), transparent)'

/** The rarity rail as navigation: each pill jumps to its section, and the one
 * whose section is under the sticky bar right now is lit (see useSectionNav).
 * Each carries how much of that rarity is unlocked — distinct cards, not
 * copies. Unselected pills are dimmed rather than recoloured, so the rarity
 * accent stays the thing that identifies a pill. */
export default function RarityNav({
  active,
  onJump,
  counts,
}: {
  active: Rarity | null
  onJump: (rarity: Rarity) => void
  counts: Map<number, number>
}) {
  const breakdown = rarityBreakdown(counts)
  const rail = useRef<HTMLDivElement>(null)

  // Scrolling the page walks the lit pill along the rail; on a phone the rail
  // is narrower than its pills, so it has to follow or the lit one hides off
  // the right edge. Horizontal only — scrollIntoView would also nudge the page.
  useEffect(() => {
    const el = rail.current
    const pill = el?.querySelector<HTMLElement>('[aria-current="true"]')
    if (!el || !pill) return
    const left = pill.offsetLeft - 12
    const right = pill.offsetLeft + pill.offsetWidth + 40 - el.clientWidth
    if (el.scrollLeft > left) el.scrollLeft = left
    else if (el.scrollLeft < right) el.scrollLeft = right
  }, [active])

  return (
    // One rail, never wrapping: on a phone the pills run off the right edge and
    // are swiped through. The mask fades a leaving pill out instead of letting
    // the scroll box slice it down the middle — it masks the pill itself, so it
    // works whatever is behind the rail. `pr-8` matches the fade, so the last
    // pill parks clear of it at the end of the swipe rather than half-ghosted;
    // `-my-1 py-1` keeps the active dot's glow out of the overflow clip.
    <div
      ref={rail}
      className="scroll-none -my-1 flex gap-2 overflow-x-auto scroll-smooth py-1 pr-8"
      style={{ maskImage: FADE_RIGHT, WebkitMaskImage: FADE_RIGHT }}
    >
      {RARITIES.map((r) => (
        <Pill
          key={r}
          label={RARITY_STYLE[r].plural}
          color={RARITY_STYLE[r].rc}
          have={breakdown[r].have}
          total={breakdown[r].total}
          active={active === r}
          onClick={() => onJump(r)}
        />
      ))}
    </div>
  )
}

function Pill({
  label,
  color,
  have,
  total,
  active,
  onClick,
}: {
  label: string
  color: string
  have: number
  total: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active}
      className={`inline-flex flex-none items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 font-mono text-[11.5px] tracking-[0.08em] transition-opacity ${
        active ? 'opacity-100' : 'opacity-50 hover:opacity-80'
      }`}
      style={{
        borderColor: hexAlpha(color, active ? 0.55 : 0.28),
        background: hexAlpha(color, active ? 0.14 : 0.05),
        color,
      }}
    >
      <i
        className="h-2 w-2 rounded-full"
        style={{ background: color, boxShadow: active ? `0 0 7px ${color}` : 'none' }}
      />
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
