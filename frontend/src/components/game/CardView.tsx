import type { CSSProperties } from 'react'

import { cardPlateHtml } from '@/lib/cardPlate'
import { RARITY_STYLE, type CardDef } from '@/lib/cards'

import LockedCard from './LockedCard'

/** One collectible card, faithful to the Claude Design "Collectible Cards" mock:
 * a rarity-tinted frame + the card's own 148px glyph plate (injected from
 * cardGlyphs.ts). `locked` renders the per-rarity «Не відкрито» design instead
 * (see LockedCard) — identity hidden, tinted in the slot's rarity. `count`
 * shows a duplicate badge. `animated` runs the plate animations; `showFlavor`
 * adds the description. `isNew` plays the one-time "just obtained" shimmer.
 *
 * `variant`: 'tile' (grid) clamps title/flavor to a reserved height so every
 * card matches; 'full' (the popped-up card, given a fixed `width`/`height`)
 * flows naturally. */
export default function CardView({
  card,
  locked = false,
  count = 0,
  animated = false,
  showFlavor = false,
  isNew = false,
  variant = 'tile',
  width,
  height,
}: {
  card: CardDef
  locked?: boolean
  count?: number
  animated?: boolean
  showFlavor?: boolean
  isNew?: boolean
  variant?: 'tile' | 'full'
  width?: number
  height?: number
}) {
  if (locked) return <LockedCard card={card} />

  const s = RARITY_STYLE[card.rarity]
  const rc = s.rc
  const animatedDot = card.rarity === 'legendary' || card.rarity === 'epic' || card.rarity === 'eternal'
  const eternalGlow = animated && card.rarity === 'eternal'
  const grid = variant === 'tile'

  const vars = { '--rc': rc, '--glow': s.glow, '--tint': s.tint, '--bd': s.border } as CSSProperties
  const frameClass = isNew ? 'card-new' : eternalGlow ? 'card-eternal-anim' : ''

  return (
    <article
      className={`relative flex flex-col overflow-hidden rounded-2xl border ${frameClass}`}
      style={{
        ...vars,
        width,
        height,
        borderColor: s.border,
        background: s.cardBg,
        boxShadow: `0 22px 46px -25px #000, 0 0 34px -15px ${s.glow}`,
      }}
    >
      {/* Top rarity rule */}
      <div
        className="h-0.5 flex-none"
        style={{ background: `linear-gradient(90deg,transparent,${rc},transparent)`, opacity: s.topOpacity }}
      />

      {/* Header: card number + rarity pill */}
      <div className="flex flex-none items-center justify-between px-4 pt-3.5">
        <span className="font-mono text-[11px] tracking-[0.14em] text-slate-500">
          № {String(card.id).padStart(2, '0')}
        </span>
        <span
          className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 font-mono text-[9.5px] uppercase tracking-[0.12em]"
          style={{ borderColor: s.border, background: s.tint, color: rc }}
        >
          <i
            className={`h-[5px] w-[5px] rounded-full ${animatedDot ? 'card-legdot' : ''}`}
            style={{ background: rc, boxShadow: card.rarity === 'common' ? 'none' : `0 0 7px ${rc}` }}
          />
          {s.label}
        </span>
      </div>

      {/* Glyph plate — injected from the mock */}
      <div
        className="contents"
        dangerouslySetInnerHTML={{ __html: cardPlateHtml(card.id, { animated, count }) }}
      />

      {/* Title + flavor. In the grid (no fixed height) both are clamped to a
          reserved line count so every card is the exact same height, whatever the
          name/description length. The popped-up card (fixed height) flows freely. */}
      <div className="flex-none px-4 pb-4 pt-0.5">
        <h3
          className={`font-display text-base font-bold leading-tight text-slate-100 ${
            grid ? 'line-clamp-2 min-h-[2.35em]' : ''
          }`}
        >
          {card.title}
        </h3>
        {showFlavor && (
          <p
            className={`mt-1.5 text-[12.5px] leading-snug text-slate-400 ${
              grid ? 'line-clamp-2 min-h-[2.6em]' : ''
            }`}
          >
            {card.flavor}
          </p>
        )}
      </div>
    </article>
  )
}
