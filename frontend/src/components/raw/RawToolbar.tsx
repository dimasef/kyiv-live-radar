import { ExternalLink } from 'lucide-react'

const BTN =
  'rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed'
// The open-in-tab twin of an export button — same accent, icon-only, tucked
// against the export it mirrors (rounded only on the outer edge).
const VIEW_BTN =
  'rounded-l-lg border border-r-0 border-phosphor/30 bg-phosphor/10 px-2 py-1.5 text-phosphor-soft transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed'

/** Counter ("показано N з M") plus the export + manual-selection controls that
 * sit above the raw-message list. Each export comes as a pair: a file download
 * and an open-in-tab (↗) twin that shows the same JSON without saving. */
export default function RawToolbar({
  loaded,
  total,
  selectedCount,
  allLoadedSelected,
  exporting,
  onExportFiltered,
  onExportSelected,
  onViewFiltered,
  onViewSelected,
  onToggleSelectAll,
  onClearSelection,
}: {
  loaded: number
  total: number | null
  selectedCount: number
  allLoadedSelected: boolean
  exporting: boolean
  onExportFiltered: () => void
  onExportSelected: () => void
  onViewFiltered: () => void
  onViewSelected: () => void
  onToggleSelectAll: () => void
  onClearSelection: () => void
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
      <span className="text-xs text-slate-400">
        Показано <span className="font-mono tabular-nums text-slate-200">{loaded}</span>
        {total != null && (
          <>
            {' з '}
            <span className="font-mono tabular-nums text-slate-200">{total}</span>
          </>
        )}
        {selectedCount > 0 && (
          <span className="ml-2 text-phosphor-soft">· вибрано {selectedCount}</span>
        )}
      </span>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={onToggleSelectAll}
          disabled={loaded === 0}
          className={`${BTN} border-white/[0.08] bg-white/[0.03] text-slate-300`}
        >
          {allLoadedSelected ? 'Зняти вибір' : 'Вибрати показані'}
        </button>
        {selectedCount > 0 && (
          <button
            onClick={onClearSelection}
            className={`${BTN} border-transparent bg-transparent text-slate-500`}
          >
            Очистити
          </button>
        )}
        <div className="flex">
          <button
            onClick={onViewSelected}
            disabled={selectedCount === 0}
            title="Відкрити вибрані у вкладці"
            aria-label="Відкрити вибрані у вкладці"
            className={VIEW_BTN}
          >
            <ExternalLink size={14} />
          </button>
          <button
            onClick={onExportSelected}
            disabled={selectedCount === 0}
            className={`${BTN} rounded-l-none border-phosphor/30 bg-phosphor/10 text-phosphor-soft`}
          >
            Експорт вибраних ({selectedCount})
          </button>
        </div>
        <div className="flex">
          <button
            onClick={onViewFiltered}
            disabled={exporting || total === 0}
            title="Відкрити фільтр у вкладці"
            aria-label="Відкрити фільтр у вкладці"
            className={VIEW_BTN}
          >
            <ExternalLink size={14} />
          </button>
          <button
            onClick={onExportFiltered}
            disabled={exporting || total === 0}
            className={`${BTN} rounded-l-none border-phosphor/30 bg-phosphor/10 text-phosphor-soft`}
          >
            {exporting ? 'Експорт…' : 'Експорт (фільтр)'}
          </button>
        </div>
      </div>
    </div>
  )
}
