import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { useDismissTransition } from '@/lib/useDismissTransition'

/** Portaled to <body> so it escapes any transformed/overflow-hidden ancestor.
 * Distinct from `chrome/MobileSheet`, which is the app's one event-feed sheet. */
export default function BottomSheet({
  onClose,
  children,
}: {
  onClose: () => void
  children: ReactNode
}) {
  const { shown, close } = useDismissTransition(onClose)
  return createPortal(
    <div
      className={`fixed inset-0 z-[1400] flex flex-col justify-end bg-ink-950/70 backdrop-blur-sm transition-opacity duration-200 sm:hidden ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`rounded-t-2xl border-t border-white/10 bg-ink-900 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-2xl transition-transform duration-300 ease-out ${
          shown ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        <div className="mx-auto mt-2 mb-1 h-1 w-9 rounded-full bg-white/15" />
        {children}
      </div>
    </div>,
    document.body,
  )
}
