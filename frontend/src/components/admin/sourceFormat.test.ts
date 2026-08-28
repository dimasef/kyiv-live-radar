import { describe, expect, it } from 'vitest'

import type { Source } from '@/api'
import type { Region, RegionInfo } from '@/types'

import { groupSourcesByRegion } from './sourceFormat'

const region = (id: Region, is_home = false, active = true): RegionInfo =>
  ({ id, name_uk: id, active, is_home, center_lat: 0, center_lon: 0 }) as RegionInfo

const source = (id: number, r: Region): Source => ({ id, region: r, name: `s${id}` }) as Source

const CATALOGUE = [
  region('kyiv', true),
  region('chernihiv'),
  region('sumy', false, false),
]

describe('grouping sources by region', () => {
  it('follows catalogue order, home first', () => {
    const groups = groupSourcesByRegion(
      [source(1, 'chernihiv'), source(2, 'kyiv')],
      CATALOGUE,
    )
    expect(groups.map((g) => g.region.id)).toEqual(['kyiv', 'chernihiv'])
  })

  it('keeps the home group even when it is empty', () => {
    const groups = groupSourcesByRegion([source(1, 'chernihiv')], CATALOGUE)
    expect(groups[0].region.id).toBe('kyiv')
    expect(groups[0].sources).toEqual([])
  })

  it('drops an empty non-home group', () => {
    // Five headings over one channel is a table of contents, not a grouping.
    const groups = groupSourcesByRegion([source(1, 'kyiv')], CATALOGUE)
    expect(groups.map((g) => g.region.id)).toEqual(['kyiv'])
  })

  it('shows a not-yet-covered region once something is tagged with it', () => {
    const groups = groupSourcesByRegion([source(1, 'sumy')], CATALOGUE)
    expect(groups.map((g) => g.region.id)).toEqual(['kyiv', 'sumy'])
    expect(groups[1].region.active).toBe(false)
  })

  it('preserves the order the server sent within a group', () => {
    // The server already sorts by (inactive last, name); re-sorting here would
    // quietly diverge from it.
    const groups = groupSourcesByRegion(
      [source(3, 'kyiv'), source(1, 'kyiv'), source(2, 'kyiv')],
      CATALOGUE,
    )
    expect(groups[0].sources.map((s) => s.id)).toEqual([3, 1, 2])
  })

  it('groups nothing while the catalogue is still loading', () => {
    expect(groupSourcesByRegion([source(1, 'kyiv')], [])).toEqual([])
  })
})
