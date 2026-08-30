import { describe, expect, it } from 'vitest'

import type { RegionInfo } from '@/types'

import { groupByRegion } from './regionGroups'

const region = (id: string, name: string): RegionInfo =>
  ({ id, name_uk: name, active: true, is_home: id === 'kyiv',
     center_lat: 50, center_lon: 30, bbox: [0, 0, 1, 1] }) as RegionInfo

const CATALOGUE = [
  region('kyiv', 'Київщина'),
  region('chernihiv', 'Чернігівщина'),
  region('sumy', 'Сумщина'),
]

const item = (id: number, r: string) => ({ id, region: r })
const regionOf = (i: { region: string }) => i.region

describe('grouping a management list by region', () => {
  it('keeps the catalogue order, not the order things arrived in', () => {
    const groups = groupByRegion(
      [item(1, 'sumy'), item(2, 'kyiv'), item(3, 'chernihiv')], CATALOGUE, regionOf,
    )
    expect(groups.map((g) => g.region?.id)).toEqual(['kyiv', 'chernihiv', 'sumy'])
  })

  it('drops a region with nothing in it', () => {
    // A heading over an empty list says what the missing heading already says,
    // and during a raid the operator is reading a list, not a contents page.
    const groups = groupByRegion([item(1, 'kyiv')], CATALOGUE, regionOf)
    expect(groups).toHaveLength(1)
    expect(groups[0].items).toHaveLength(1)
  })

  it('renders un-grouped while the catalogue is still loading', () => {
    // Never blank: the catalogue arrives on its own fetch, and this list is
    // where an operator cancels a live false positive.
    const groups = groupByRegion([item(1, 'kyiv'), item(2, 'sumy')], [], regionOf)
    expect(groups).toEqual([{ region: null, items: [item(1, 'kyiv'), item(2, 'sumy')] }])
  })

  it('still shows a row whose region the catalogue does not know', () => {
    // A stored row from before that region was declared. Hiding it would make
    // it impossible to cancel.
    const groups = groupByRegion(
      [item(1, 'kyiv'), item(2, 'atlantis')], CATALOGUE, regionOf,
    )
    expect(groups.map((g) => g.region?.id ?? null)).toEqual(['kyiv', null])
    expect(groups[1].items).toEqual([item(2, 'atlantis')])
  })

  it('has nothing to group when the list is empty', () => {
    expect(groupByRegion([], CATALOGUE, regionOf)).toEqual([])
  })
})
