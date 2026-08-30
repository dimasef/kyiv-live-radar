import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react'

/** The title row of «Весь фід», doubling as the fold control for the stats /
 * filters / toolbar block beneath it, and carrying the reload button.
 *
 * Folded, it still carries the two numbers that would otherwise be the reason
 * to unfold — how much of the filtered set is loaded, and how much is selected
 * — so folding costs no orientation, only the controls themselves.
 *
 * Reload lives HERE rather than in the toolbar for the same reason: the feed is
 * still arriving while the page is open, and refreshing it must not depend on
 * the controls being unfolded. A row, not a button wrapping everything: the
 * fold control and the reload are two buttons, and one cannot be nested in the
 * other.
 */
export default function ControlsToggle({
  open,
  onToggle,
  loaded,
  total,
  selectedCount,
  loading,
  onReload,
}: {
  open: boolean
  onToggle: () => void
  loaded: number
  total: number | null
  selectedCount: number
  loading: boolean
  onReload: () => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
      >
        {open ? (
          <ChevronDown size={16} className="shrink-0 text-slate-500" />
        ) : (
          <ChevronRight size={16} className="shrink-0 text-slate-500" />
        )}
        <h1 className="font-display text-lg font-bold text-slate-100">Сирі повідомлення</h1>
        {!open && (
          <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-500">
            {loaded}
            {total != null && <span className="text-slate-600">/{total}</span>}
            {selectedCount > 0 && (
              <span className="ml-1.5 text-phosphor/80">+{selectedCount}</span>
            )}
          </span>
        )}
      </button>

      <button
        onClick={onReload}
        disabled={loading}
        aria-label="Оновити фід"
        title="Оновити фід"
        className="flex flex-none items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:text-slate-100 disabled:opacity-40"
      >
        <RotateCcw size={13} className={loading ? 'animate-spin' : undefined} />
        Оновити
      </button>
    </div>
  )
}
