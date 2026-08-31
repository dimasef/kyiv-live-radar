import { describe, expect, it } from 'vitest'

import type { Region, RegionInfo } from '@/types'

import {
  currentRegion,
  effectiveRegion,
  framingBounds,
  insideWatchedRegions,
  regionBounds,
  regionLabel,
} from './regions'

const region = (id: Region, is_home = false): RegionInfo =>
  ({
    id,
    name_uk: id === 'kyiv' ? 'Київщина' : 'Харківщина',
    active: true,
    is_home,
    center_lat: 50,
    center_lon: 30,
    bbox: [49, 29, 51, 32],
  }) as RegionInfo

const CATALOGUE = [region('kyiv', true), region('kharkiv')]

describe('which region the reader follows', () => {
  it('is the one they chose', () => {
    expect(effectiveRegion(CATALOGUE, 'kharkiv')).toBe('kharkiv')
  })

  it('falls back to the deployment region before they have chosen', () => {
    // The first paint happens before the picker is answered; an empty feed and
    // a map framed on nothing would be a worse default than the home region.
    expect(effectiveRegion(CATALOGUE, null)).toBe('kyiv')
  })

  it('is null only when the catalogue has not loaded either', () => {
    expect(effectiveRegion([], null)).toBeNull()
  })

  it('reads the same answer straight off the store shape', () => {
    expect(currentRegion({ regions: CATALOGUE, chosenRegion: 'kharkiv' })).toBe('kharkiv')
  })
})

describe('map framing', () => {
  it('turns a catalogue bbox into Leaflet corner pairs', () => {
    expect(regionBounds(CATALOGUE, 'kyiv')).toEqual([
      [49, 29],
      [51, 32],
    ])
  })

  it('returns null for an unknown region so the caller keeps its default', () => {
    expect(regionBounds(CATALOGUE, 'sumy')).toBeNull()
    expect(regionBounds(CATALOGUE, null)).toBeNull()
  })
})

describe('labels', () => {
  it('falls back to the raw id before the catalogue loads', () => {
    expect(regionLabel([], 'kyiv')).toBe('kyiv')
    expect(regionLabel(CATALOGUE, 'kyiv')).toBe('Київщина')
  })
})

describe('what the map is framed on', () => {
  const UA: [[number, number], [number, number]] = [
    [44.2, 22.1],
    [52.4, 40.3],
  ]

  it('frames the chosen region once the catalogue has answered', () => {
    expect(framingBounds(CATALOGUE, 'kharkiv', UA)).toEqual(
      regionBounds(CATALOGUE, 'kharkiv'),
    )
    expect(framingBounds(CATALOGUE, 'kharkiv', UA)).not.toEqual(UA)
  })

  it('frames the whole country before the catalogue has answered', () => {
    // The bug, exactly: the catalogue is FETCHED, so it is empty at first
    // paint on every single reload. A reader following Сумщина opened on Kyiv
    // every time, because the fallback was the Kyiv city box and the "not yet"
    // branch was in fact the only branch that ever ran (2026-08-29).
    expect(framingBounds([], 'kharkiv', UA)).toEqual(UA)
  })

  it('frames the whole country when the reader has chosen nothing', () => {
    // NOT the home region — that is what `currentRegion` is for, and it stays
    // right for the feed and for push. On the map, an unanswered picker framed
    // on one oblast hides the other four off-screen.
    expect(framingBounds(CATALOGUE, null, UA)).toEqual(UA)
  })

  it('frames the whole country for a region the catalogue does not declare', () => {
    expect(framingBounds(CATALOGUE, 'nowhere' as never, UA)).toEqual(UA)
  })
})

describe('sanity-checking a GNSS fix before it becomes a home', () => {
  it('accepts a point inside a watched region', () => {
    expect(insideWatchedRegions(CATALOGUE, 50.45, 30.52)).toBe(true)
  })

  it('rejects a jammed fix in another country', () => {
    // The reason this check exists: electronic warfare is routine over Ukraine
    // during exactly the raids this app is for, and a jammed fix arrives
    // looking like a good one — no error, plausible accuracy, coordinates in
    // China. Silently stamping a home from it moves the danger radius and the
    // push gate somewhere the reader has never been.
    expect(insideWatchedRegions(CATALOGUE, 39.9, 116.4)).toBe(false)
  })

  it('rejects a point just outside every box', () => {
    expect(insideWatchedRegions(CATALOGUE, 51.5, 30)).toBe(false)
  })

  it('rejects everything while the catalogue is still empty', () => {
    // Fails CLOSED, unlike the helpers above: their fallback costs a label
    // rendered as an id, this one would cost a wrong home.
    expect(insideWatchedRegions([], 50.45, 30.52)).toBe(false)
  })
})
