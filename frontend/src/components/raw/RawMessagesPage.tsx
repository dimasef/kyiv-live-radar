import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchRawSources } from '@/api'
import type { RawOutcomeFilter, RawSource } from '@/types'

import LlmStatsStrip from './LlmStatsStrip'
import RawFilterBar from './RawFilterBar'
import RawMessageRow from './RawMessageRow'
import RawToolbar from './RawToolbar'
import { useRawMessages } from './useRawMessages'
import { useRawSelection } from './useRawSelection'

const SEARCH_DEBOUNCE_MS = 300

/** Hidden debug route (/raw): every ingested message, including ones the
 * parser suppressed or couldn't localize — distinct from the operator-facing
 * event feed, which only shows messages that became a live sighting. */
export default function RawMessagesPage() {
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [outcome, setOutcome] = useState<RawOutcomeFilter | 'all'>('all')
  const [llm, setLlm] = useState<'all' | 'yes' | 'no'>('all')
  const [sourceId, setSourceId] = useState<number | 'all'>('all')
  const [sources, setSources] = useState<RawSource[]>([])

  useEffect(() => {
    const t = setTimeout(() => setQ(searchInput.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    fetchRawSources().then(setSources).catch(() => {})
  }, [])

  const filters = useMemo(() => ({ q, outcome, llm, sourceId }), [q, outcome, llm, sourceId])
  const { items, loading, done, total, loadMore, apiFilter } = useRawMessages(filters)
  const selection = useRawSelection({ items, filters, apiFilter, sources })
  const sentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore()
      },
      { rootMargin: '400px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [loadMore])

  return (
    <div className="h-[100dvh] overflow-y-auto overscroll-contain bg-ink-950 px-4 py-8 text-slate-200">
      <div className="mx-auto max-w-3xl">
        <h1 className="font-display text-lg font-bold text-slate-100">Сирі повідомлення</h1>
        <p className="mt-1 text-xs text-slate-500">
          Усі вхідні повідомлення, включно з тими, що не потрапили у Стрічку подій.
        </p>

        <LlmStatsStrip />

        <RawFilterBar
          search={searchInput}
          onSearchChange={setSearchInput}
          outcome={outcome}
          onOutcomeChange={setOutcome}
          llm={llm}
          onLlmChange={setLlm}
          sources={sources}
          sourceId={sourceId}
          onSourceIdChange={setSourceId}
        />

        <RawToolbar
          loaded={items.length}
          total={total}
          selectedCount={selection.selectedCount}
          allLoadedSelected={selection.allLoadedSelected}
          exporting={selection.exporting}
          onExportFiltered={selection.exportFiltered}
          onExportSelected={selection.exportSelected}
          onViewFiltered={selection.viewFiltered}
          onViewSelected={selection.viewSelected}
          onToggleSelectAll={selection.toggleSelectAll}
          onClearSelection={selection.clearSelection}
        />

        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <RawMessageRow
              key={item.id}
              item={item}
              selected={selection.selectedIds.has(item.id)}
              onToggleSelect={selection.toggleSelect}
            />
          ))}
        </ul>

        {!loading && items.length === 0 && (
          <div className="py-10 text-center text-xs text-slate-500">Нічого не знайдено.</div>
        )}

        <div ref={sentinelRef} className="h-10" />
        {loading && <div className="py-4 text-center text-xs text-slate-500">Завантаження…</div>}
        {done && items.length > 0 && (
          <div className="py-4 text-center text-xs text-slate-600">Це все.</div>
        )}
      </div>
    </div>
  )
}
