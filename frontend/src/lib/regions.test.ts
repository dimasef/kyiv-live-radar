import { describe, expect, it } from 'vitest'

import type { Region, RegionInfo } from '@/types'

import { currentRegion, effectiveRegion, regionBounds, regionLabel } from './regions'

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
