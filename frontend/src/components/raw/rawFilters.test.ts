import { describe, expect, it } from 'vitest'

import type { RawSource } from '@/types'

import { sourcesInRegions } from './rawFilters'

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
