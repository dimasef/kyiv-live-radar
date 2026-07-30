import type { CSSProperties } from 'react'

import { cardPlateHtml } from '@/lib/cardPlate'
import { RARITY_STYLE, type CardDef } from '@/lib/cards'

/** One collectible card, faithful to the Claude Design "Collectible Cards" mock:
 * a rarity-tinted frame + the card's own 148px glyph plate (injected from
 * cardGlyphs.ts). `locked` hides the identity entirely — no rarity, no title,
 * an indeterminate "?" instead of the glyph. `count` shows a duplicate badge.
 * `animated` runs the plate animations; `showFlavor` adds the description.
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
  variant = 'tile',
  width,
  height,
}: {
  card: CardDef
  locked?: boolean
  count?: number
  animated?: boolean
  showFlavor?: boolean
  variant?: 'tile' | 'full'
  width?: number
  height?: number
}) {
  const s = RARITY_STYLE[card.rarity]
  const rc = locked ? '#3a4453' : s.rc
  const glow = locked ? 'transparent' : s.glow
  const tint = locked ? 'rgba(148,163,184,.04)' : s.tint
  const border = locked ? 'rgba(255,255,255,.06)' : s.border
  const animatedDot = !locked && (card.rarity === 'legendary' || card.rarity === 'epic' || card.rarity === 'eternal')
  const grid = variant === 'tile'

  const vars = { '--rc': rc, '--glow': glow, '--tint': tint, '--bd': border } as CSSProperties

  return (
    <article
      className="relative flex flex-col overflow-hidden rounded-2xl border"
      style={{
        ...vars,
        width,
        height,
        borderColor: border,
        background: locked ? 'linear-gradient(180deg,#0e131a,#0a0d12)' : s.cardBg,
        boxShadow: locked
          ? '0 22px 46px -28px #000'
          : `0 22px 46px -25px #000, 0 0 34px -15px ${s.glow}`,
      }}
    >
      {/* Top rarity rule */}
      <div
        className="h-0.5 flex-none"
        style={{ background: `linear-gradient(90deg,transparent,${rc},transparent)`, opacity: locked ? 0.4 : s.topOpacity }}
      />

      {/* Header: card number + rarity pill */}
      <div className="flex flex-none items-center justify-between px-4 pt-3.5">
        <span className="font-mono text-[11px] tracking-[0.14em] text-slate-500">
          № {String(card.id).padStart(2, '0')}
        </span>
        <span
          className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 font-mono text-[9.5px] uppercase tracking-[0.12em]"
          style={{ borderColor: border, background: tint, color: rc }}
        >
          <i
            className={`h-[5px] w-[5px] rounded-full ${animatedDot ? 'card-legdot' : ''}`}
            style={{ background: rc, boxShadow: locked || card.rarity === 'common' ? 'none' : `0 0 7px ${rc}` }}
          />
          {locked ? '???' : s.label}
        </span>
      </div>

      {/* Glyph plate — injected from the mock, or an indeterminate placeholder */}
      {locked ? (
        <div
          className="relative m-3.5 flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-white/[0.06]"
          style={{ minHeight: 148, background: 'radial-gradient(120% 90% at 50% 30%, rgba(148,163,184,.04), #080b0f 72%)' }}
        >
          <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,rgba(255,255,255,.035)_0_1px,transparent_1px_4px)]" />
          <div className="absolute h-[118px] w-[118px] rounded-full border border-white/5" />
          <span className="relative select-none font-display text-6xl font-bold text-slate-700">?</span>
        </div>
      ) : (
        <div
          className="contents"
          dangerouslySetInnerHTML={{ __html: cardPlateHtml(card.id, { animated, count }) }}
        />
      )}

      {/* Title + flavor. In the grid (no fixed height) both are clamped to a
          reserved line count so every card is the exact same height, whatever the
          name/description length. The popped-up card (fixed height) flows freely. */}
      <div className="flex-none px-4 pb-4 pt-0.5">
        <h3
          className={`font-display text-base font-bold leading-tight text-slate-100 ${
            grid ? 'line-clamp-2 min-h-[2.35em]' : ''
          }`}
        >
          {locked ? <span className="text-slate-600">???</span> : card.title}
        </h3>
        {showFlavor && (grid || !locked) && (
          <p
            className={`mt-1.5 text-[12.5px] leading-snug text-slate-400 ${
              grid ? 'line-clamp-2 min-h-[2.6em]' : ''
            }`}
          >
            {/* Locked cards keep the reserved space (equal height) but reveal nothing. */}
            {locked ? '' : card.flavor}
          </p>
        )}
      </div>
    </article>
  )
}
