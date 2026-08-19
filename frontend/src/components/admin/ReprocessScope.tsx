import type { ReprocessPreview } from '@/api'
import { kyivStamp } from '@/lib/kyivTime'

/** Default tail: a few hundred messages is roughly one night of a busy raid —
 * the stretch still on the map, which is what a parser fix is usually judged on. */
export const DEFAULT_LAST = 300

/** Picks how much history a reprocess touches: the last N messages (leaving
 * everything older alone) or the whole log.
 *
 * The readout below the control matters as much as the control: the server
 * widens "last N" so no track is cut in half, so the number that actually
 * replays is often larger than the one typed here, and the operator should see
 * that before pressing a destructive button. */
export default function ReprocessScope({
  last,
  onChange,
  preview,
}: {
  last: number | null
  onChange: (last: number | null) => void
  preview: ReprocessPreview | null
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2 text-slate-300">
        <ScopeButton active={last != null} onClick={() => onChange(DEFAULT_LAST)}>
          Останні
        </ScopeButton>
        <input
          type="number"
          min={1}
          value={last ?? ''}
          disabled={last == null}
          onChange={(e) => onChange(Math.max(1, Number(e.target.value) || 1))}
          className="w-20 rounded-md border border-white/15 bg-ink-900 px-2 py-1 font-mono text-xs text-slate-200 disabled:opacity-40"
          aria-label="Скільки останніх повідомлень перебудувати"
        />
        <span className="text-slate-500">повідомлень</span>
        <ScopeButton active={last == null} onClick={() => onChange(null)}>
          Усі
        </ScopeButton>
      </div>
      <p className="mt-1.5 text-slate-500">{scopeLine(last, preview)}</p>
    </div>
  )
}

function scopeLine(last: number | null, preview: ReprocessPreview | null): string {
  if (preview == null) return 'Рахую обсяг…'
  if (last == null) return `Перебудує всі ${preview.raw_messages} повідомлень — усю історію.`
  const n = preview.scope_messages
  if (n == null || preview.scope_from == null) return 'Немає збережених повідомлень.'
  const widened = n > last ? ' Межу зсунуто назад, щоб не розрізати трек навпіл.' : ''
  return `Перебудує ${n} повідомлень, починаючи з ${kyivStamp(preview.scope_from)}. Старіше не зміниться.${widened}`
}

function ScopeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-2 py-1 font-medium transition-colors ${
        active
          ? 'border-phosphor/40 bg-phosphor/10 text-phosphor-soft'
          : 'border-white/15 bg-white/[0.04] text-slate-400 hover:bg-white/[0.08]'
      }`}
    >
      {children}
    </button>
  )
}
