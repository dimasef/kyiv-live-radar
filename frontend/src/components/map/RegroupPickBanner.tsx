import { useEffect } from 'react'

import { useRadar } from '@/store'

/** The map is armed to receive a sighting: say which one, and offer a way out.
 *
 * Pick mode changes what a click on every target means, so it must be
 * unmistakable while it lasts and trivially cancellable — a raid is not the
 * moment to discover the map has a mode. */
export default function RegroupPickBanner() {
  const pick = useRadar((s) => s.regroupPick)
  const cancelRegroupPick = useRadar((s) => s.cancelRegroupPick)

  // Captured, like Overlay's — the editor underneath is Escape-dismissable too,
  // and cancelling the pick must not take it down as well.
  useEffect(() => {
    if (!pick) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      cancelRegroupPick()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [pick, cancelRegroupPick])

  if (!pick) return null

  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-[1500] flex justify-center px-3">
      <div className="pointer-events-auto flex items-center gap-3 rounded-xl border border-phosphor/40 bg-ink-900/95 px-3 py-2 text-xs text-slate-200 shadow-2xl backdrop-blur-sm">
        <span>
          Оберіть на мапі ціль, до якої приєднати{' '}
          <span className="font-mono text-phosphor-soft">M{pick.eventId}</span>
        </span>
        <button
          onClick={cancelRegroupPick}
          className="rounded border border-white/15 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 hover:text-slate-200"
        >
          відміна
        </button>
      </div>
    </div>
  )
}
