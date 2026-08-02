import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { useDismissTransition } from '@/lib/useDismissTransition'

type Tone = 'danger' | 'warn' | 'accent' | 'neutral'

const CONFIRM_BTN: Record<Tone, string> = {
  danger: 'bg-rose-500/90 text-white hover:bg-rose-500',
  warn: 'bg-amber-500/90 text-ink-950 hover:bg-amber-500',
  accent: 'bg-phosphor text-ink-950 hover:opacity-90',
  neutral: 'bg-white/15 text-slate-100 hover:bg-white/25',
}

/** In-app confirmation dialog replacing window.confirm — a portalled,
 * theme-matched modal (mirrors AuthModal). Mounted only while asking;
 * confirm/cancel both close it. `cancelLabel` defaults to Ukrainian for the
 * admin call sites; i18n'd callers pass their own. */
export default function ConfirmModal({
  message,
  confirmLabel,
  cancelLabel = 'Скасувати',
  tone = 'neutral',
  onConfirm,
  onCancel,
}: {
  /** Plain text for most call sites; a node when the question needs to SHOW
   * something (the avatar prompt previews what's being replaced). */
  message: ReactNode
  confirmLabel: string
  cancelLabel?: string
  tone?: Tone
  onConfirm: () => void
  onCancel: () => void
}) {
  const { shown, close } = useDismissTransition(onCancel)

  const confirm = () => {
    onConfirm()
    close()
  }

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        className={`w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl transition-all duration-200 ease-out ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-sm leading-relaxed text-slate-200">{message}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={close}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-sm font-medium text-slate-300 hover:bg-white/[0.06]"
          >
            {cancelLabel}
          </button>
          <button
            onClick={confirm}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${CONFIRM_BTN[tone]}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
