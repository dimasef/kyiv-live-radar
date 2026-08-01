import type { Rarity } from '@/lib/cards'

/** The signature motion for one rarity, rendered inside the card frame.
 *
 * Only mounted on the single-card view (CardView `animated`), never on grid
 * tiles: thirty-two cards each running their own loop is both noisy and a
 * measurable amount of compositing. Common returns nothing by design — a still
 * card is what makes the others read as rare.
 *
 * `eternal` is absent here because its effect is a glow on the frame itself
 * (`.card-eternal-anim` on the <article>), not an overlay. */
export default function RarityFlourish({ rarity }: { rarity: Rarity }) {
  // `rare` is deliberately absent: its signature is the glyph pulse, applied to
  // the injected plate itself (see cardPlate.ts). Giving it the travelling
  // border too made rare and legendary read as the same card.
  if (rarity === 'legendary') return <span className="card-flow-border" aria-hidden />
  if (rarity === 'epic') return <EpicArcs />
  return null
}

/** Three lightning arcs down the card's edges. `preserveAspectRatio="none"`
 * stretches the 100×100 viewBox to whatever the card is, so the arcs stay
 * pinned to the corners at any card size. */
function EpicArcs() {
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden
      className="card-arcs"
    >
      <g
        fill="none"
        stroke="#e9d5ff"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ filter: 'drop-shadow(0 0 4px var(--rc))' }}
      >
        <path d="M9 4 L17 26 L9 31 L21 58" />
        <path d="M91 8 L82 30 L90 35 L77 66" />
        <path d="M32 94 L40 74 L31 69 L45 47" />
      </g>
    </svg>
  )
}
