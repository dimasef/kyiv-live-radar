import type { ReactNode } from 'react'
import { useState } from 'react'

import ConfirmModal from '@/components/common/ConfirmModal'

type Tone = 'danger' | 'neutral' | 'accent' | 'warn'

const TONE: Record<Tone, string> = {
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20',
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
  accent: 'border-phosphor/40 bg-phosphor/10 text-phosphor-soft hover:bg-phosphor/20',
  neutral: 'border-white/15 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]',
}

/** A button that runs an async admin action, disables itself while in flight,
 * and surfaces a failure inline (admin tools are single-user — a tiny error
 * line beats a toast system). The store updates from the server's WS broadcast,
 * so `onRun` just needs to fire the request. When `confirm` is set, the click
 * opens an in-app ConfirmModal (not the browser's window.confirm) first. */
export default function AdminActionButton({
  label,
  onRun,
  tone = 'neutral',
  confirm,
  compact = false,
  title,
  icon,
}: {
  label: string
  onRun: () => Promise<unknown>
  tone?: Tone
  confirm?: string
  /** Sized to sit inside a chip rather than in a row of its own. */
  compact?: boolean
  /** Tooltip — worth setting when `compact` shrinks the label to a glyph. */
  title?: string
  /** Leading glyph, dropped while pending/failed so the state owns the button. */
  icon?: ReactNode
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)
  const [asking, setAsking] = useState(false)

  const execute = async () => {
    setPending(true)
    setError(false)
    try {
      await onRun()
    } catch {
      setError(true)
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <button
        onClick={() => (confirm ? setAsking(true) : execute())}
        disabled={pending}
        title={title}
        // The full-size variant is a 36px thumb target, not a 26px mouse
        // target: this console is used one-handed on a phone mid-raid, and
        // «Скасувати ціль» sitting a few pixels from «Видалити» is not a
        // mistake worth making with a finger. `compact` stays as it was — it
        // exists to sit INSIDE a chip, where it is never the primary target.
        className={`inline-flex items-center justify-center gap-1 rounded-lg border font-medium transition-colors duration-150 disabled:opacity-40 ${
          compact ? 'px-1 py-0 text-[10px] leading-4' : 'h-9 px-3 text-xs'
        } ${error ? TONE.danger : TONE[tone]}`}
      >
        {icon && !pending && !error && icon}
        {error ? (compact ? '!' : 'Помилка') : pending ? '…' : label}
      </button>
      {asking && confirm && (
        <ConfirmModal
          message={confirm}
          confirmLabel={label}
          tone={tone}
          onConfirm={execute}
          onCancel={() => setAsking(false)}
        />
      )}
    </>
  )
}
