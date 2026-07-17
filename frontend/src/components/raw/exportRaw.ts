import type { RawMessage, RawSource } from '@/types'

import type { RawMessageFilters } from './useRawMessages'

/** The JSON file an export produces — a filter-context header plus the raw
 * messages verbatim, so it's self-describing when handed off for analysis. */
export interface RawExportEnvelope {
  scope: 'filtered' | 'selected'
  exported_at: string
  filters: {
    search: string | null
    channel: string
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

function describeFilters(filters: RawMessageFilters, sources: RawSource[]) {
  const channel =
    filters.sourceId === 'all'
      ? 'усі канали'
      : (sources.find((s) => s.id === filters.sourceId)?.name ?? `#${filters.sourceId}`)
  return {
    search: filters.q.trim() || null,
    channel,
    outcome: OUTCOME_LABEL[filters.outcome] ?? filters.outcome,
    llm: LLM_LABEL[filters.llm] ?? filters.llm,
  }
}

interface ExportParams {
  scope: 'filtered' | 'selected'
  filters: RawMessageFilters
  sources: RawSource[]
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
    filters: describeFilters(params.filters, params.sources),
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
