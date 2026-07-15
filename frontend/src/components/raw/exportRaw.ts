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

/** Build the export envelope and trigger a browser download of it as JSON.
 * `scope` distinguishes a full filtered export from a hand-picked selection;
 * both carry the same filter context so the file always says what it is. */
export function downloadRawExport(params: {
  scope: 'filtered' | 'selected'
  filters: RawMessageFilters
  sources: RawSource[]
  messages: RawMessage[]
  truncated: boolean
}) {
  const envelope: RawExportEnvelope = {
    scope: params.scope,
    exported_at: new Date().toISOString(),
    filters: describeFilters(params.filters, params.sources),
    count: params.messages.length,
    truncated: params.truncated,
    messages: params.messages,
  }
  const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `raw-${params.scope}-${envelope.exported_at.replace(/[:.]/g, '-')}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
