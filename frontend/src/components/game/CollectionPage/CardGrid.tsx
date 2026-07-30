import type { CardDef } from '@/lib/cards'

import CardView from '../CardView'

/** The card grid: 2/3/4 columns; owned cards are buttons that pop up, locked
 * ones are inert placeholders. */
export default function CardGrid({
  cards,
  counts,
  onSelect,
}: {
  cards: CardDef[]
  counts: Map<number, number>
  onSelect: (card: CardDef) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {cards.map((card) => {
        const count = counts.get(card.id)
        const locked = count == null
        const tile = <CardView card={card} locked={locked} count={count ?? 0} showFlavor />
        return locked ? (
          <div key={card.id}>{tile}</div>
        ) : (
          <button
            key={card.id}
            onClick={() => onSelect(card)}
            className="rounded-2xl text-left transition-transform duration-200 hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40"
          >
            {tile}
          </button>
        )
      })}
    </div>
  )
}
