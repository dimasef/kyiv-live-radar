import Overlay from '@/components/common/Overlay'
import type { CardDef } from '@/lib/cards'

import CardView from './CardView'

/** The popped-up, full-size card — shared by tapping a card in the collection
 * and by a fresh reveal after an analysis. Closes on backdrop/Esc. `caption`
 * shows a small heading above it (e.g. "Нова картка" on a reveal). */
export default function CardModal({
  card,
  count = 0,
  caption,
  onClose,
}: {
  card: CardDef
  count?: number
  caption?: string
  onClose: () => void
}) {
  return (
    <Overlay onClose={onClose} className="rise flex flex-col items-center gap-3">
      {caption && <p className="panel-title">{caption}</p>}
      <CardView card={card} count={count} variant="full" animated showFlavor width={255} height={310} />
    </Overlay>
  )
}
