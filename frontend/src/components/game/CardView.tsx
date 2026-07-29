import type { CSSProperties } from 'react'

import { RARITY_STYLE, type CardDef } from '@/lib/cards'

import CardGlyph from './CardGlyph'

/** One collectible card, faithful to the Claude Design "Collectible Cards" mock:
 * a rarity-tinted frame with a radar glyph plate (scanline + ring + glyph).
 *
 * `locked` keeps the frame but hides the identity entirely — no rarity, no
 * title, and an INDETERMINATE mark ("?") instead of the card's own glyph, so an
 * unearned card gives nothing away. `count` shows a duplicate badge when >1.
 * `animated` runs the radar sweep — ONLY the popped-up card animates; grid tiles
 * stay still. `showFlavor` adds the description line. `width`/`height` fix the
 * card size (the glyph plate flexes to fill) — used by the popped-up modal. */
export default function CardView({
  card,
  locked = false,
  count = 0,
  animated = false,
  showFlavor = false,
  width,
  height,
}: {
  card: CardDef
  locked?: boolean
  count?: number
  animated?: boolean
  showFlavor?: boolean
  width?: number
  height?: number
}) {
  const s = RARITY_STYLE[card.rarity]
  const rc = locked ? '#3a4453' : s.rc
  const glow = locked ? 'transparent' : s.glow
  const tint = locked ? 'rgba(148,163,184,.04)' : s.tint
  const border = locked ? 'rgba(255,255,255,.06)' : s.border
  const filled = height != null // plate flexes to fill a fixed-height card

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
      {count > 1 && (
        <span
          className="absolute right-2.5 top-2.5 z-10 rounded-full px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-950"
          style={{ background: s.rc }}
        >
          ×{count}
        </span>
      )}

      {/* Top rarity rule */}
      <div
        className="h-0.5 flex-none"
        style={{
          background: `linear-gradient(90deg,transparent,${rc},transparent)`,
          opacity: locked ? 0.4 : s.topOpacity,
        }}
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
            className={`h-[5px] w-[5px] rounded-full ${!locked && card.rarity === 'legendary' ? 'card-legdot' : ''}`}
            style={{ background: rc, boxShadow: locked || card.rarity === 'common' ? 'none' : `0 0 7px ${rc}` }}
          />
          {locked ? '???' : s.label}
        </span>
      </div>

      {/* Glyph plate */}
      <div
        className={`relative m-3.5 flex items-center justify-center overflow-hidden rounded-xl border border-white/[0.06] ${filled ? 'min-h-0 flex-1' : ''}`}
        style={{
          ...(filled ? {} : { height: 148 }),
          background: `radial-gradient(120% 90% at 50% 30%, ${tint}, ${locked ? '#080b0f' : s.plateEnd} 72%)`,
        }}
      >
        <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,rgba(255,255,255,.035)_0_1px,transparent_1px_4px)]" />
        <div className="absolute h-[118px] w-[118px] rounded-full border border-white/5" />
        {!locked && animated && (
          <div
            className="card-sweep absolute inset-x-0 h-11"
            style={{ background: `linear-gradient(180deg,transparent,${rc},transparent)`, opacity: 0.1 }}
          />
        )}
        {locked ? (
          <span className="relative select-none font-mono text-6xl font-light text-slate-700">?</span>
        ) : (
          <CardGlyph id={card.id} size={70} />
        )}
      </div>

      {/* Title (+ flavor only in the popped-up view) */}
      <div className="flex-none px-4 pb-4 pt-0.5">
        <h3 className="font-display text-base font-bold leading-tight text-slate-100">
          {locked ? <span className="text-slate-600">???</span> : card.title}
        </h3>
        {showFlavor && !locked && (
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-400">{card.flavor}</p>
        )}
      </div>
    </article>
  )
}
