import { describe, expect, it } from 'vitest'

import type { Region, RegionInfo } from '@/types'

import {
  isInFeed,
  isPinnedRegion,
  migrateFeedRegions,
  pruneFeedRegions,
  shownRegions,
} from './feedRegions'

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

describe('the chip state a reader outside the home region sees', () => {
  // Reported 2026-08-29: after switching the followed region to Сумщина, its
  // chip in Налаштування → Стрічка подій could not be turned on.
  //
  // Three components computed "always in the feed" as `region.is_home` — the
  // DEPLOYMENT's home (Київщина) — while the store computed it as the region
  // the reader FOLLOWS. For a reader on Сумщина the two disagree, so its chip
  // rendered off while `toggleFeedRegion` treated it as the pinned one and
  // returned early: stuck off, and clicking did nothing.
  const CATALOGUE = [info('kyiv', true), info('chernihiv'), info('sumy')]
  const home = (id: Region) => CATALOGUE.find((r) => r.id === id)!.is_home

  it('pins the FOLLOWED region and not the deployment home', () => {
    expect(isPinnedRegion('sumy', 'sumy')).toBe(true)
    expect(isPinnedRegion('kyiv', 'sumy')).toBe(false)
    // The bug, stated as the disagreement it was: for this reader the
    // catalogue flag and the real answer point at different regions.
    expect(home('sumy')).toBe(false)
    expect(home('kyiv')).toBe(true)
  })

  it('shows the followed region in the feed with no extras chosen', () => {
    expect(isInFeed('sumy', [], 'sumy')).toBe(true)
    // ...and this is what rendered false before, on a chip that then refused
    // to toggle because the store considered it pinned.
    expect(home('sumy') || [].includes('sumy' as never)).toBe(false)
  })

  it('still lets that reader add and drop the other regions', () => {
    expect(isInFeed('kyiv', ['kyiv'], 'sumy')).toBe(true)
    expect(isInFeed('chernihiv', ['kyiv'], 'sumy')).toBe(false)
    expect(isPinnedRegion('kyiv', 'sumy')).toBe(false)
  })

  it('agrees with the catalogue for a reader who stayed on the home region', () => {
    for (const r of CATALOGUE) {
      expect(isPinnedRegion(r.id, 'kyiv')).toBe(r.is_home)
    }
    expect(shownRegions(['chernihiv'], 'kyiv')).toEqual(['kyiv', 'chernihiv'])
  })

  it('never lists the followed region twice when a stale extra names it', () => {
    expect(shownRegions(['sumy', 'chernihiv'], 'sumy')).toEqual(['sumy', 'chernihiv'])
  })

  it('offers every declared region as a chip, home or not', () => {
    expect(pruneFeedRegions(['sumy'], CATALOGUE)).toEqual(['sumy'])
  })
})
