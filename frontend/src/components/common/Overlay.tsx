import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { useDismissTransition } from '@/lib/useDismissTransition'

/** A centered modal shell: a portalled, fading backdrop that closes on click or
 * Escape, wrapping content that stops propagation. Callers style the content via
 * `className` (e.g. a `rise` card or a bare card). Replaces the repeated
 * `createPortal(<div fixed inset-0 … onClick=close><div stopPropagation>…)`. */
export default function Overlay({
  onClose,
  className = '',
  children,
}: {
  onClose: () => void
  className?: string
  children: ReactNode
}) {
  const { shown, close } = useDismissTransition(onClose)

  // Captured at the window so this runs BEFORE anything listening in the bubble
  // phase, and the event is then consumed: an overlay opened over another
  // Escape-dismissable surface (the settings drawer) must close itself alone,
  // not take that surface down with it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      close()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [close])

  return createPortal(
    <div
      className={`fixed inset-0 z-[3000] flex items-center justify-center bg-ink-950/80 p-6 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div onClick={(e) => e.stopPropagation()} className={className}>
        {children}
      </div>
    </div>,
    document.body,
  )
}
