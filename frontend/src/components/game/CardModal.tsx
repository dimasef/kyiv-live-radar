import Overlay from '@/components/common/Overlay'
import type { CardDef } from '@/lib/cards'

import CardView from './CardView'

/** The popped-up, full-size card — shared by tapping a card in the collection
 * and by a fresh reveal after an analysis. Closes on backdrop/Esc. `caption`
 * shows a small heading above it (e.g. "Нова картка" on a reveal). `action`
 * adds a primary button under the card (e.g. "До колекції" on a reveal). */
export default function CardModal({
  card,
  count = 0,
  caption,
  action,
  onClose,
}: {
  card: CardDef
  count?: number
  caption?: string
  action?: { label: string; onClick: () => void }
  onClose: () => void
}) {
  return (
    <Overlay onClose={onClose} className="rise flex flex-col items-center gap-3">
      {caption && <p className="panel-title">{caption}</p>}
      <CardView card={card} count={count} variant="full" animated showFlavor width={255} height={310} />
      {action && (
        <button
          onClick={action.onClick}
          className="mt-1 w-[255px] rounded-lg border border-phosphor/25 bg-phosphor/[0.08] px-4 py-2 text-sm text-phosphor-soft transition-colors hover:border-phosphor/40"
        >
          {action.label}
        </button>
      )}
    </Overlay>
  )
}
