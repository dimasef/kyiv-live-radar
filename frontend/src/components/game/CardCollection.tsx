import { Info, X } from 'lucide-react'
import { useState } from 'react'
import { createPortal } from 'react-dom'

import { CARDS, type CardDef } from '@/lib/cards'
import { useRadar } from '@/store'

import CardView from './CardView'

/** How cards are earned — shown from the "Колекція" info button. */
const RULES = [
  'Увімкни «Гейміфікацію» в налаштуваннях (потрібен вхід в акаунт).',
  'На карті клікни ціль — БПЛА, ракету або балістику.',
  'Натисни «Аналіз», поки ціль у польоті, або «Аналіз рештків», коли її збили чи загубили.',
  'Сканування триває кілька секунд — і ти отримуєш випадкову картку.',
  'З однієї цілі можна зробити 2 аналізи (політ + рештки). Перший, хто встиг, забирає картку.',
  'Рідкісні картки трапляються рідше за звичайні.',
  'Цілі, старші за 12 годин, аналізувати вже не можна.',
  'Дублікати не зникають — вони накопичуються (× кількість).',
]

/** The signed-in user's card collection on the account page: the full deck with
 * earned cards revealed (and a duplicate count) and the rest locked. Clicking an
 * earned card pops it up enlarged, with its description and the radar sweep
 * animation. The info button explains how cards are earned. */
export default function CardCollection() {
  const collection = useRadar((s) => s.collection)
  const counts = new Map((collection?.cards ?? []).map((c) => [c.card_id, c.count]))
  const owned = counts.size
  const total = collection?.card_count ?? CARDS.length
  const [selected, setSelected] = useState<CardDef | null>(null)
  const [showRules, setShowRules] = useState(false)

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="font-mono text-xs text-slate-500">
          Зібрано <span className="text-phosphor-soft">{owned}</span> з {total}
        </p>
        <button
          onClick={() => setShowRules(true)}
          aria-label="Як отримати картки"
          title="Як отримати картки"
          className="flex h-6 w-6 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
        >
          <Info size={15} />
        </button>
      </div>

      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(180px,1fr))]">
        {CARDS.map((card) => {
          const count = counts.get(card.id)
          const locked = count == null
          const tile = <CardView card={card} locked={locked} count={count ?? 0} />
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
              <CardView card={selected} count={counts.get(selected.id) ?? 0} animated showFlavor width={255} height={310} />
            </div>
          </div>,
          document.body,
        )}

      {showRules &&
        createPortal(
          <div
            className="fixed inset-0 z-[3000] flex items-center justify-center bg-ink-950/80 p-6 backdrop-blur-sm"
            onClick={() => setShowRules(false)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="rise w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl"
            >
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-display text-sm font-bold text-slate-100">Як отримати картки</h3>
                <button
                  onClick={() => setShowRules(false)}
                  aria-label="Закрити"
                  className="text-slate-400 transition-colors hover:text-slate-100"
                >
                  <X size={18} />
                </button>
              </div>
              <ol className="flex list-decimal flex-col gap-2 pl-4 text-[13px] leading-relaxed text-slate-300 marker:font-mono marker:text-slate-600">
                {RULES.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ol>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
