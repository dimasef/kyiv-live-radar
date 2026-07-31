import Overlay from '@/components/common/Overlay'
import type { CardDef } from '@/lib/cards'

import CardView from './CardView'

/** The popped-up, full-size card — shared by tapping a card in the collection
 * and by a fresh reveal after an analysis. Closes on backdrop/Esc. `caption`
 * shows a small heading above it (e.g. "Нова картка" on a reveal); `captionGlow`
 * gives it the golden glow used for a NEW card. `action` adds a primary button
 * under the card (e.g. "До колекції"); `closeLabel`, when set, adds a secondary
 * close button beside it. */
export default function CardModal({
  card,
  count = 0,
  caption,
  captionGlow = false,
  action,
  closeLabel,
  onClose,
}: {
  card: CardDef
  count?: number
  caption?: string
  captionGlow?: boolean
  action?: { label: string; onClick: () => void }
  closeLabel?: string
  onClose: () => void
}) {
  return (
    <Overlay onClose={onClose} className="rise flex flex-col items-center gap-3">
      {caption && <p className={`panel-title ${captionGlow ? 'card-reveal-gold' : ''}`}>{caption}</p>}
      <CardView card={card} count={count} variant="full" animated showFlavor width={255} height={310} />
      {action && (
        <div className="mt-1 flex w-[255px] gap-2">
          <button
            onClick={action.onClick}
            className="flex-1 rounded-lg border border-phosphor/25 bg-phosphor/[0.08] px-4 py-2 text-sm text-phosphor-soft transition-colors hover:border-phosphor/40"
          >
            {action.label}
          </button>
          {closeLabel && (
            <button
              onClick={onClose}
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-slate-300 transition-colors hover:border-white/20 hover:text-slate-100"
            >
              {closeLabel}
            </button>
          )}
        </div>
      )}
    </Overlay>
  )
}
