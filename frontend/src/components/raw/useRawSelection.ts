import { useCallback, useEffect, useMemo, useState } from 'react'

import { fetchRawExport } from '@/api'
import type { RawMessagesFilter } from '@/api'
import type { RawMessage, RawSource } from '@/types'

import { downloadRawExport } from './exportRaw'
import type { RawMessageFilters } from './useRawMessages'

/** Manual row selection + the two export paths for /raw. `exportFiltered` asks
 * the server for the whole filtered slice (not just the loaded pages);
 * `exportSelected` ships exactly the hand-picked rows. Both go through the
 * same download envelope so the file always carries its filter context. */
export function useRawSelection(params: {
  items: RawMessage[]
  filters: RawMessageFilters
  apiFilter: RawMessagesFilter
  sources: RawSource[]
}) {
  const { items, filters, apiFilter, sources } = params
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [exporting, setExporting] = useState(false)

  // A selection only makes sense against the dataset it was made in — reset it
  // when the filter changes (which also resets the visible list underneath it).
  useEffect(() => setSelectedIds(new Set()), [apiFilter])

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const allSelected = items.length > 0 && items.every((i) => prev.has(i.id))
      return allSelected ? new Set() : new Set(items.map((i) => i.id))
    })
  }, [items])

  const selectedItems = useMemo(
    () => items.filter((i) => selectedIds.has(i.id)),
    [items, selectedIds],
  )
  const allLoadedSelected = items.length > 0 && selectedItems.length === items.length

  const exportSelected = useCallback(() => {
    if (selectedItems.length === 0) return
    downloadRawExport({
      scope: 'selected',
      filters,
      sources,
      messages: selectedItems,
      truncated: false,
    })
  }, [filters, sources, selectedItems])

  const exportFiltered = useCallback(async () => {
    setExporting(true)
    try {
      const res = await fetchRawExport(apiFilter)
      downloadRawExport({
        scope: 'filtered',
        filters,
        sources,
        messages: res.messages,
        truncated: res.truncated,
      })
    } finally {
      setExporting(false)
    }
  }, [apiFilter, filters, sources])

  return {
    selectedIds,
    selectedCount: selectedItems.length,
    allLoadedSelected,
    exporting,
    toggleSelect,
    clearSelection,
    toggleSelectAll,
    exportSelected,
    exportFiltered,
  }
}
