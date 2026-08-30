import type { RawMessage, RawSource, RegionInfo } from '@/types'

import type { RawMessageFilters } from './useRawMessages'

/** The JSON file an export produces — a filter-context header plus the raw
 * messages verbatim, so it's self-describing when handed off for analysis. */
export interface RawExportEnvelope {
  scope: 'filtered' | 'selected'
  exported_at: string
  filters: {
    search: string | null
    /** Comma-separated names, or «усі джерела» — several can be picked. */
    sources: string
    /** Comma-separated oblasts, or «усі області». */
    regions: string
    outcome: string
    llm: string
  }
  count: number
  /** true = the server export cap was hit, so `messages` is a partial set. */
  truncated: boolean
  messages: RawMessage[]
}

const OUTCOME_LABEL: Record<string, string> = {
  all: 'усі',
  event: 'подія',
  suppressed: 'не подія',
}
const LLM_LABEL: Record<string, string> = { all: 'усі', yes: 'так', no: 'ні' }

function describeFilters(
  filters: RawMessageFilters,
  sources: RawSource[],
  regions: RegionInfo[],
) {
  // Every picked value is spelled out, not counted: an export of one oblast's
  // night is a different document from an export of everything, and a file that
  // says «2 області» gets read as the wrong one of the two months later.
  const pickedSources = filters.sourceIds.length
    ? filters.sourceIds.map((id) => sources.find((s) => s.id === id)?.name ?? `#${id}`).join(', ')
    : 'усі джерела'
  const pickedRegions = filters.regions.length
    ? filters.regions.map((id) => regions.find((r) => r.id === id)?.name_uk ?? id).join(', ')
    : 'усі області'
  return {
    search: filters.q.trim() || null,
    sources: pickedSources,
    regions: pickedRegions,
    outcome: OUTCOME_LABEL[filters.outcome] ?? filters.outcome,
    llm: LLM_LABEL[filters.llm] ?? filters.llm,
  }
}

interface ExportParams {
  scope: 'filtered' | 'selected'
  filters: RawMessageFilters
  sources: RawSource[]
  regions: RegionInfo[]
  messages: RawMessage[]
  truncated: boolean
}

/** Build the self-describing export envelope + its pretty JSON blob URL. Both
 * the download and the open-in-tab paths share this, so they produce byte-for-
 * byte the same content — only the delivery differs. */
function exportBlobUrl(params: ExportParams): { url: string; envelope: RawExportEnvelope } {
  const envelope: RawExportEnvelope = {
    scope: params.scope,
    exported_at: new Date().toISOString(),
    filters: describeFilters(params.filters, params.sources, params.regions),
    count: params.messages.length,
    truncated: params.truncated,
    messages: params.messages,
  }
  const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: 'application/json' })
  return { url: URL.createObjectURL(blob), envelope }
}

/** Trigger a browser download of the export as a `.json` file. */
export function downloadRawExport(params: ExportParams) {
  const { url, envelope } = exportBlobUrl(params)
  const a = document.createElement('a')
  a.href = url
  a.download = `raw-${params.scope}-${envelope.exported_at.replace(/[:.]/g, '-')}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Open the export as JSON in a browser tab — no file saved. When the export
 * needs an async fetch first (the filtered scope), the caller must pre-open a
 * blank tab IN the click handler and pass it here, or the popup is blocked; the
 * sync selected scope can let this open the tab itself. The blob URL is revoked
 * on a delay so the tab has time to load it. */
export function openRawExport(params: ExportParams, tab?: Window | null) {
  const { url } = exportBlobUrl(params)
  const win = tab ?? window.open()
  if (win == null) {
    URL.revokeObjectURL(url)
    return
  }
  win.location.href = url
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
