const BTN =
  'rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed'

/** Counter ("показано N з M") plus the export + manual-selection controls that
 * sit above the raw-message list. */
export default function RawToolbar({
  loaded,
  total,
  selectedCount,
  allLoadedSelected,
  exporting,
  onExportFiltered,
  onExportSelected,
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
        <button
          onClick={onExportSelected}
          disabled={selectedCount === 0}
          className={`${BTN} border-phosphor/30 bg-phosphor/10 text-phosphor-soft`}
        >
          Експорт вибраних ({selectedCount})
        </button>
        <button
          onClick={onExportFiltered}
          disabled={exporting || total === 0}
          className={`${BTN} border-phosphor/30 bg-phosphor/10 text-phosphor-soft`}
        >
          {exporting ? 'Експорт…' : 'Експорт (фільтр)'}
        </button>
      </div>
    </div>
  )
}
