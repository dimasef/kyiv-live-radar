import { Radar } from 'lucide-react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import Overlay from '@/components/common/Overlay'
import { cardById } from '@/lib/cards'
import { COLLECTION_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

import CardModal from './CardModal'

/** Global gamification overlays, mounted once in the app shell so they survive
 * route changes while a 3–10s analysis runs: the scanning overlay while it
 * works, then the card-reveal (or "someone beat you to it" notice). Reads the
 * whole flow from the game slice — the button only kicks it off. */
export default function AnalysisLayer() {
  const analyzing = useRadar((s) => s.analyzing)
  const reveal = useRadar((s) => s.reveal)
  const claimError = useRadar((s) => s.claimError)

  if (analyzing) return <ScanningOverlay />
  if (reveal || claimError) return <ResultModal />
  return null
}

function ScanningOverlay() {
  const { t } = useTranslation()
  const kind = useRadar((s) => s.analyzing?.kind)
  // Deliberately NOT a full opaque/blurred block, and pointer-events-none: an
  // analysis runs up to 10s and must never hide the air-alert banner. A light
  // scrim keeps the map (and any alert) readable underneath while it animates.
  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-[3000] flex flex-col items-center justify-center gap-5 bg-ink-950/45">
      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inset-0 animate-ping rounded-full border border-phosphor/40" />
        <span className="absolute inset-3 animate-pulse rounded-full border border-phosphor/25" />
        <Radar size={44} className="animate-spin text-phosphor-soft" style={{ animationDuration: '3s' }} />
      </div>
      <div className="text-center">
        <p className="font-display text-sm font-bold text-slate-100">
          {kind === 'remains' ? t('game.scanningRemains') : t('game.scanning')}
        </p>
        <p className="mt-1 font-mono text-[11px] text-slate-500">{t('game.scanningHint')}</p>
      </div>
    </div>,
    document.body,
  )
}

function ResultModal() {
  const { t } = useTranslation()
  const reveal = useRadar((s) => s.reveal)
  const claimError = useRadar((s) => s.claimError)
  const dismiss = useRadar((s) => s.dismissReveal)

  const card = reveal ? cardById(reveal.cardId) : undefined
  if (card && reveal) {
    const toCollection = () => {
      dismiss()
      navigate(COLLECTION_PATH)
    }
    return (
      <CardModal
        card={card}
        count={reveal.count}
        caption={reveal.isNew ? t('game.newCard') : t('game.dupCard')}
        captionGlow={reveal.isNew}
        action={{ label: t('game.toCollection'), onClick: toCollection }}
        closeLabel={t('game.close')}
        onClose={dismiss}
      />
    )
  }

  // A lost race / error — a short message, no card.
  return (
    <Overlay
      onClose={dismiss}
      className="rise w-full max-w-xs rounded-2xl border border-white/10 bg-ink-900 p-5 text-center shadow-2xl"
    >
      <p className="py-2 text-sm text-slate-300">
        {claimError === 'taken' ? t('game.takenBody') : t('game.errorBody')}
      </p>
      <button
        onClick={dismiss}
        className="mt-3 w-full rounded-lg border border-phosphor/25 bg-phosphor/[0.08] px-4 py-2 text-sm text-phosphor-soft transition-colors hover:border-phosphor/40"
      >
        {t('game.close')}
      </button>
    </Overlay>
  )
}
