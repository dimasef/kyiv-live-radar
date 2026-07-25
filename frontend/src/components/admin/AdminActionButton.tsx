import { useState } from 'react'

type Tone = 'danger' | 'neutral' | 'accent'

const TONE: Record<Tone, string> = {
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20',
  accent: 'border-phosphor/40 bg-phosphor/10 text-phosphor-soft hover:bg-phosphor/20',
  neutral: 'border-white/15 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]',
}

/** A button that runs an async admin action, disables itself while in flight,
 * and surfaces a failure inline (admin tools are single-user — a tiny error
 * line beats a toast system). The store updates from the server's WS broadcast,
 * so `onRun` just needs to fire the request. */
export default function AdminActionButton({
  label,
  onRun,
  tone = 'neutral',
  confirm,
}: {
  label: string
  onRun: () => Promise<unknown>
  tone?: Tone
  confirm?: string
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)

  const run = async () => {
    if (confirm && !window.confirm(confirm)) return
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
    <button
      onClick={run}
      disabled={pending}
      className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors duration-150 disabled:opacity-40 ${
        error ? TONE.danger : TONE[tone]
      }`}
    >
      {error ? 'Помилка' : pending ? '…' : label}
    </button>
  )
}
