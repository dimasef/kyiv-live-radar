import { describe, expect, it } from 'vitest'

import type { Region, RegionInfo } from '@/types'

import { migrateFeedRegions, pruneFeedRegions, shownRegions } from './feedRegions'

const info = (id: Region, is_home = false): RegionInfo =>
  ({ id, name_uk: id, active: true, is_home, center_lat: 0, center_lon: 0 }) as RegionInfo

describe('migrating the feed region filter off the old boolean', () => {
  it('reads the stored set when there is one', () => {
    expect(migrateFeedRegions('["sumy","chernihiv"]', '0')).toEqual(['sumy', 'chernihiv'])
  })

  it('takes a fresh install to what the boolean defaulted to', () => {
    // The old default was ON — the reader had been seeing the north, and a
    // filter that starts hiding data is a filter nobody knows is there.
    expect(migrateFeedRegions(null, null)).toEqual(['chernihiv'])
  })

  it('honours an explicit opt-out from the old boolean', () => {
    expect(migrateFeedRegions(null, '0')).toEqual([])
  })

  it('honours an explicit opt-in from the old boolean', () => {
    expect(migrateFeedRegions(null, '1')).toEqual(['chernihiv'])
  })

  it('falls back to the boolean when the stored set is corrupt', () => {
    // Not to [] — that would silently hide a region the reader had chosen.
    expect(migrateFeedRegions('{not json', '1')).toEqual(['chernihiv'])
  })

  it('ignores non-string members of a stored set', () => {
    expect(migrateFeedRegions('["sumy",7,null]', null)).toEqual(['sumy'])
  })
})

describe('pruning against the server catalogue', () => {
  it('drops an id the server no longer declares', () => {
    // One stale id 422s the whole /events/recent page, and bootstrap swallows
    // that into a silently empty feed.
    expect(pruneFeedRegions(['chernihiv', 'atlantis' as Region], [info('chernihiv')])).toEqual([
      'chernihiv',
    ])
  })

  it('leaves the choice alone while the catalogue is still loading', () => {
    expect(pruneFeedRegions(['chernihiv'], [])).toEqual(['chernihiv'])
  })
})

describe('which regions the feed shows', () => {
  it('always includes home, first', () => {
    expect(shownRegions(['chernihiv'], 'kyiv')).toEqual(['kyiv', 'chernihiv'])
  })

  it('never lists home twice, even if it leaked into the stored set', () => {
    expect(shownRegions(['kyiv', 'sumy'], 'kyiv')).toEqual(['kyiv', 'sumy'])
  })

  it('sends just the extras before the catalogue names a home', () => {
    expect(shownRegions(['chernihiv'], null)).toEqual(['chernihiv'])
  })
})
