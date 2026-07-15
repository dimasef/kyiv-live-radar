import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { fetchRawCount, fetchRawMessages } from '@/api'
import type { RawMessagesFilter } from '@/api'
import type { RawMessage, RawOutcomeFilter } from '@/types'

export interface RawMessageFilters {
  q: string
  outcome: RawOutcomeFilter | 'all'
  llm: 'yes' | 'no' | 'all'
  sourceId: number | 'all'
}

/** UI filter state ('all' sentinels) -> API params (fields simply omitted).
 * Shared by the list, the count, and the export so all three query the same
 * slice of data. */
export function toApiFilter(f: RawMessageFilters): RawMessagesFilter {
  return {
    q: f.q || undefined,
    outcome: f.outcome === 'all' ? undefined : f.outcome,
    llm: f.llm === 'all' ? undefined : f.llm,
    sourceId: f.sourceId === 'all' ? undefined : f.sourceId,
  }
}

/** Cursor-paginated raw-message list. Changing `filters` restarts the list
 * from scratch — a new search/filter is a new query, not more of the old
 * one. `loadMore` is idempotent while a page is in flight or the list is
 * exhausted, so an IntersectionObserver can call it on every scroll tick. */
export function useRawMessages(filters: RawMessageFilters) {
  const [items, setItems] = useState<RawMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  // Total matching the filter (server-side), independent of how many pages
  // have scrolled into view — null until the count for the current filter
  // lands. Powers the "показано N з M" counter.
  const [total, setTotal] = useState<number | null>(null)
  // Refs, not state: mutate synchronously so a page in flight when filters
  // change can tell it's been superseded and discard its response instead
  // of appending stale results onto the fresh (reset) list.
  const cursorRef = useRef<number | undefined>(undefined)
  const requestIdRef = useRef(0)

  const apiFilter = useMemo(
    () => toApiFilter(filters),
    [filters.q, filters.outcome, filters.llm, filters.sourceId],
  )

  const fetchPage = useCallback(
    (requestId: number) => {
      setLoading(true)
      fetchRawMessages({ beforeId: cursorRef.current, ...apiFilter })
        .then((page) => {
          if (requestId !== requestIdRef.current) return
          setItems((prev) => [...prev, ...page.items])
          cursorRef.current = page.next_before_id ?? undefined
          if (page.next_before_id == null) setDone(true)
        })
        .catch(() => {
          if (requestId === requestIdRef.current) setDone(true)
        })
        .finally(() => {
          if (requestId === requestIdRef.current) setLoading(false)
        })
    },
    [apiFilter],
  )

  const loadMore = useCallback(() => {
    if (loading || done) return
    fetchPage(requestIdRef.current)
  }, [loading, done, fetchPage])

  useEffect(() => {
    requestIdRef.current += 1
    cursorRef.current = undefined
    setItems([])
    setDone(false)
    setTotal(null)
    fetchPage(requestIdRef.current)
    const requestId = requestIdRef.current
    fetchRawCount(apiFilter)
      .then((r) => {
        if (requestId === requestIdRef.current) setTotal(r.count)
      })
      .catch(() => {})
  }, [fetchPage, apiFilter])

  return { items, loading, done, total, loadMore, apiFilter }
}
