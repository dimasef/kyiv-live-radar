import { describe, expect, it } from 'vitest'

import type { RawSource } from '@/types'

import {
  filtersFromSearch,
  filtersToSearch,
  hasActiveFilters,
  NO_RAW_FILTERS,
  sourcesInRegions,
} from './rawFilters'
import type { RawMessageFilters } from './useRawMessages'

const kyiv: RawSource = { id: 1, name: 'Київ', regions: ['kyiv'] }
const north: RawSource = { id: 2, name: 'Чернігів', regions: ['chernihiv'] }
// A Kyiv channel that also narrates the northern approach — the reason a source
// carries a LIST of regions rather than one.
const both: RawSource = { id: 3, name: 'Київ+Північ', regions: ['kyiv', 'chernihiv'] }
const ALL = [kyiv, north, both]

describe('narrowing the source filter by region', () => {
  it('offers every source when no region is picked', () => {
    // The empty set is the filter's off position, not "match nothing".
    expect(sourcesInRegions(ALL, [])).toEqual(ALL)
  })

  it('keeps a source bound to the picked region', () => {
    expect(sourcesInRegions(ALL, ['chernihiv'])).toEqual([north, both])
  })

  it('matches on an EXTRA binding, not only the primary', () => {
    // Dropping `both` from a Chernihiv pick would hide the very channel that
    // reports most of what lands there.
    expect(sourcesInRegions(ALL, ['chernihiv'])).toContain(both)
  })

  it('unions several picked regions', () => {
    expect(sourcesInRegions(ALL, ['kyiv', 'chernihiv'])).toEqual(ALL)
  })

  it('can legitimately come back empty', () => {
    // Which is why the control says so instead of silently showing every source.
    expect(sourcesInRegions(ALL, ['sumy'])).toEqual([])
  })
})

describe('filters <-> URL', () => {
  const full: RawMessageFilters = {
    q: 'ТЕЦ 6',
    outcome: 'suppressed',
    llm: 'yes',
    sourceIds: [13, 12],
    regions: ['kyiv', 'chernihiv'],
  }

  it('omits every filter that is in its off position', () => {
    expect(filtersToSearch(NO_RAW_FILTERS)).toBe('')
  })

  it('round-trips a fully specified filter', () => {
    expect(filtersFromSearch(`?${filtersToSearch(full)}`)).toEqual(full)
  })

  it('reads an empty query string as no filter at all', () => {
    expect(filtersFromSearch('')).toEqual(NO_RAW_FILTERS)
  })

  it('falls back to the off position for a value it does not know', () => {
    // The URL is hand-editable; a garbled param must not leave the operator
    // staring at an empty list with nothing on screen explaining why.
    const f = filtersFromSearch('?outcome=whatever&llm=maybe&sources=abc,-1&q=%20%20')
    expect(f).toEqual(NO_RAW_FILTERS)
  })

  it('keeps the good values in a partly broken list', () => {
    expect(filtersFromSearch('?sources=13,abc,7').sourceIds).toEqual([13, 7])
  })

  it('says when anything is filtered', () => {
    expect(hasActiveFilters(NO_RAW_FILTERS)).toBe(false)
    expect(hasActiveFilters({ ...NO_RAW_FILTERS, regions: ['sumy'] })).toBe(true)
    expect(hasActiveFilters({ ...NO_RAW_FILTERS, q: 'ТЕЦ' })).toBe(true)
  })
})
