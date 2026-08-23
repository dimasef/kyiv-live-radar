import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { fetchRawCount, fetchRawMessages } from '@/api'
import type { RawMessagesFilter } from '@/api'
import type { RawMessage, RawOutcomeFilter, Threat } from '@/types'

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

  // Destructured so the memo depends on the filter VALUES, not the object's
  // identity — the caller rebuilds `filters` every render, and keying on it
  // would restart the whole query on each one. Rebuilding the object inside
  // also means a newly added filter field fails to compile here rather than
  // silently missing from the dependencies.
  const { q, outcome, llm, sourceId } = filters
  const apiFilter = useMemo(
    () => toApiFilter({ q, outcome, llm, sourceId }),
    [q, outcome, llm, sourceId],
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

  /** Drop a deleted sighting from the row that produced it, in place — a
   * refetch here would restart the cursor and throw away everything the admin
   * scrolled to. `outcome` is the server's own diagnosis, so it isn't
   * recomputed: the row is just relabelled as one an admin took the event off,
   * until the next real fetch says otherwise. */
  const dropEvent = useCallback((messageId: number, eventId: number) => {
    setItems((prev) =>
      prev.map((m) => {
        if (m.id !== messageId) return m
        const events = m.events.filter((e) => e.event_id !== eventId)
        const emptied = events.length === 0 && m.notice_id == null
        return { ...m, events, outcome: emptied ? 'знято' : m.outcome }
      }),
    )
  }, [])

  /** Attach or clear the notice a row traces to, in place — same reason as
   * `dropEvent`: a refetch would throw away the scroll position. */
  const setNotice = useCallback(
    (messageId: number, notice: { id: number; kind: string } | null) => {
      setItems((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, notice_id: notice?.id ?? null, notice_kind: notice?.kind ?? null }
            : m,
        ),
      )
    },
    [],
  )

  /** Re-point a sighting's chip at the track it was just moved to. Same
   * in-place reasoning as `dropEvent`: the admin is deep in a scrolled list and
   * a refetch would restart the cursor from the top. */
  const moveEventToTrack = useCallback((eventId: number, threatId: number) => {
    setItems((prev) =>
      prev.map((m) =>
        m.events.some((e) => e.event_id === eventId)
          ? {
              ...m,
              events: m.events.map((e) =>
                e.event_id === eventId ? { ...e, threat_id: threatId } : e,
              ),
            }
          : m,
      ),
    )
  }, [])

  /** Fold a track's fresh server state into every chip that belongs to it —
   * across ALL loaded rows, since one track's sightings are scattered over as
   * many messages as reported it. Without this a retype in the editor changed
   * nothing visible in the list and read as a no-op. */
  const applyTrack = useCallback((track: Threat) => {
    setItems((prev) =>
      prev.map((m) =>
        m.events.some((e) => e.threat_id === track.id)
          ? {
              ...m,
              events: m.events.map((e) =>
                e.threat_id === track.id
                  ? {
                      ...e,
                      threat_target_type: track.target_type,
                      threat_status: track.status,
                      threat_closed_reason: track.closed_reason ?? null,
                      incident_id: track.incident_id ?? null,
                      corroboration_count: track.corroboration_count,
                      confidence: track.confidence,
                    }
                  : e,
              ),
            }
          : m,
      ),
    )
  }, [])

  return {
    items,
    loading,
    done,
    total,
    loadMore,
    apiFilter,
    dropEvent,
    setNotice,
    moveEventToTrack,
    applyTrack,
  }
}
