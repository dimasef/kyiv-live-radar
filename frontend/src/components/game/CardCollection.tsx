import { useState } from 'react'
import { createPortal } from 'react-dom'

import { CARDS, type CardDef } from '@/lib/cards'
import { useRadar } from '@/store'

import CardView from './CardView'

/** The signed-in user's card collection on the account page: the full deck with
 * earned cards revealed (and a duplicate count) and the rest locked. Clicking an
 * earned card pops it up enlarged, with its description and the radar sweep
 * animation — grid tiles themselves stay static. */
export default function CardCollection() {
  const collection = useRadar((s) => s.collection)
  const counts = new Map((collection?.cards ?? []).map((c) => [c.card_id, c.count]))
  const owned = counts.size
  const total = collection?.card_count ?? CARDS.length
  const [selected, setSelected] = useState<CardDef | null>(null)

  return (
    <div>
      <p className="mb-3 font-mono text-xs text-slate-500">
        Зібрано <span className="text-phosphor-soft">{owned}</span> з {total}
      </p>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(180px,1fr))]">
        {CARDS.map((card) => {
          const count = counts.get(card.id)
          const locked = count == null
          const tile = <CardView card={card} locked={locked} count={count ?? 0} />
          // Only earned cards pop up; locked placeholders are inert.
          return locked ? (
            <div key={card.id}>{tile}</div>
          ) : (
            <button
              key={card.id}
              onClick={() => setSelected(card)}
              className="rounded-2xl text-left transition-transform duration-200 hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40"
            >
              {tile}
            </button>
          )
        })}
      </div>

      {selected &&
        createPortal(
          <div
            className="fixed inset-0 z-[3000] flex items-center justify-center bg-ink-950/80 p-6 backdrop-blur-sm"
            onClick={() => setSelected(null)}
          >
            <div className="rise" onClick={(e) => e.stopPropagation()}>
              <CardView
                card={selected}
                count={counts.get(selected.id) ?? 0}
                animated
                showFlavor
                width={255}
                height={310}
              />
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
