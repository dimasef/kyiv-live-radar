import type { CSSProperties } from "react";

import { RARITY_RGB, type CardDef } from "@/lib/cards";

/** The «Невідомо» (undiscovered) card, faithful to the Claude Design v2 mock:
 * a dashed frame, a lock-icon rarity pill, a "?" glyph plate and skeleton
 * title/flavor bars — the whole thing tinted in the slot's own rarity accent so
 * every rarity gets its own locked look, while the card's identity stays hidden.
 *
 * Its height matches an owned tile (same 148px plate + a title bar + two flavor
 * lines), so a mixed owned/locked grid stays perfectly aligned. */
export default function LockedCard({ card }: { card: CardDef }) {
  const rgb = RARITY_RGB[card.rarity];
  const a = (alpha: number) => `rgba(${rgb}, ${alpha})`;
  const vars = { "--lr": rgb } as CSSProperties;

  return (
    <article
      className="relative flex flex-col overflow-hidden rounded-2xl border border-dashed"
      style={{
        ...vars,
        borderColor: a(0.26),
        background: "linear-gradient(180deg,#0b0e13,#080a0e)",
        boxShadow: "0 22px 46px -28px #000",
      }}
    >
      <div
        className="h-0.5 flex-none"
        style={{
          background: `linear-gradient(90deg,transparent,${a(0.32)},transparent)`,
          opacity: 0.45,
        }}
      />

      <div className="flex flex-none items-center justify-between px-4 pt-3.5">
        <span className="font-mono text-[11px] tracking-[0.14em]" style={{ color: a(0.42) }}>
          № {String(card.id).padStart(2, "0")}
        </span>
        <span
          className="inline-flex items-center rounded-full border border-dashed px-2 py-1 font-mono text-[9.5px] uppercase tracking-[0.12em]"
          style={{ borderColor: a(0.32), background: a(0.05), color: a(0.6) }}
        >
          Невідомо
        </span>
      </div>

      <div
        className="relative m-3.5 flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-dashed"
        style={{
          minHeight: 148,
          borderColor: a(0.14),
          background: `radial-gradient(120% 90% at 50% 30%, ${a(0.06)}, #070a0e 74%)`,
        }}
      >
        <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,rgba(255,255,255,.03)_0_1px,transparent_1px_4px)]" />
        <div
          className="absolute h-[118px] w-[118px] rounded-full border border-dashed"
          style={{ borderColor: a(0.12) }}
        />
        <span
          className="relative select-none font-display text-[58px] font-bold leading-none"
          style={{ color: a(0.24), textShadow: "0 0 22px rgba(0,0,0,.6)" }}
        >
          ?
        </span>
      </div>

      {/* Skeleton title + flavor. Reserves the SAME vertical space as an owned
          tile's title/flavor block (min-h-[2.35em] + min-h-[2.6em] with the same
          paddings) so a mixed owned/locked grid stays perfectly aligned. */}
      <div className="flex-none px-4 pb-4 pt-0.5">
        <div className="min-h-[2.35em]">
          <div
            className="h-[15px] w-[58%] rounded-[5px]"
            style={{ background: `linear-gradient(90deg,${a(0.2)},${a(0.05)})` }}
          />
        </div>
        <div className="mt-1.5 flex min-h-[2.6em] flex-col gap-1.5 text-[12.5px]">
          <div className="h-2 w-[90%] rounded" style={{ background: a(0.07) }} />
          <div className="h-2 w-[64%] rounded" style={{ background: a(0.07) }} />
        </div>
      </div>
    </article>
  );
}
