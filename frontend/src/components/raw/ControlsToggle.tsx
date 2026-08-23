import { ChevronDown, ChevronRight } from 'lucide-react'

/** The title row of «Весь фід», doubling as the fold control for the stats /
 * filters / toolbar block beneath it.
 *
 * Folded, it still carries the two numbers that would otherwise be the reason
 * to unfold — how much of the filtered set is loaded, and how much is selected
 * — so folding costs no orientation, only the controls themselves. */
export default function ControlsToggle({
  open,
  onToggle,
  loaded,
  total,
  selectedCount,
}: {
  open: boolean
  onToggle: () => void
  loaded: number
  total: number | null
  selectedCount: number
}) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center gap-1.5 text-left"
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
  )
}
