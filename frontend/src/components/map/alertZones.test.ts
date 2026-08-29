import { describe, expect, it } from 'vitest'

import type { AlertZone, Region } from '@/types'

import {
  alertedZones,
  compactSinceLabel,
  inShownRegions,
  sinceParts,
  zoneFitBounds,
  zoneTone,
} from './alertZones'

const zone = (over: Partial<AlertZone> = {}): AlertZone => ({
  zone_id: 'kyiv-obl-vyshhorodskyi',
  name_uk: 'Вишгородський район',
  oblast: 'Київська область',
  region: 'kyiv',
  alert: false,
  changed_at: null,
  stale: false,
  ...over,
})

describe('zoneTone', () => {
  it('reads an unreachable provider as its own tone, never as an all-clear', () => {
    expect(zoneTone(zone({ alert: false, stale: true }))).toBe('stale')
    // Even a zone we last saw under alert: stale means "we no longer know".
    expect(zoneTone(zone({ alert: true, stale: true }))).toBe('stale')
  })

  it('paints a live siren and a live all-clear apart', () => {
    expect(zoneTone(zone({ alert: true }))).toBe('alert')
    expect(zoneTone(zone({ alert: false }))).toBe('clear')
  })
})

describe('sinceParts', () => {
  const now = Date.parse('2026-08-19T16:00:00Z')

  it('splits the held duration into hours and minutes', () => {
    expect(sinceParts('2026-08-19T13:09:00Z', now)).toEqual({ h: 2, m: 51 })
    expect(sinceParts('2026-08-19T15:42:00Z', now)).toEqual({ h: 0, m: 18 })
  })

  it('says nothing when the provider never reported a transition', () => {
    expect(sinceParts(null, now)).toBeNull()
  })

  it('says nothing rather than a negative age when the clocks disagree', () => {
    expect(sinceParts('2026-08-19T16:05:00Z', now)).toBeNull()
  })
})

describe('alertedZones', () => {
  it('counts only zones under a siren we can currently vouch for', () => {
    const zones = {
      a: zone({ zone_id: 'a', alert: true, changed_at: '2026-08-19T13:00:00Z' }),
      b: zone({ zone_id: 'b', alert: false }),
      c: zone({ zone_id: 'c', alert: true, stale: true }),
      d: zone({ zone_id: 'd', alert: true, changed_at: '2026-08-19T15:00:00Z' }),
    }
    expect(alertedZones(zones).map((z) => z.zone_id)).toEqual(['d', 'a'])
  })
})


describe('compactSinceLabel', () => {
  // The standing centre label shows ONE unit — «1 год 20 хв» stays with the
  // hover caption, which has room for it.
  it('shows minutes alone below the hour', () => {
    expect(compactSinceLabel({ h: 0, m: 20 })).toEqual({ key: 'zones.compactM', vars: { m: 20 } })
    expect(compactSinceLabel({ h: 0, m: 59 })).toEqual({ key: 'zones.compactM', vars: { m: 59 } })
  })

  it('drops to whole hours past the hour, rounding rather than flooring', () => {
    // Flooring would call 1:50 "1г" for the better part of an hour, reading as
    // newer than it is.
    expect(compactSinceLabel({ h: 1, m: 5 })).toEqual({ key: 'zones.compactH', vars: { h: 1 } })
    expect(compactSinceLabel({ h: 1, m: 29 })).toEqual({ key: 'zones.compactH', vars: { h: 1 } })
    expect(compactSinceLabel({ h: 1, m: 30 })).toEqual({ key: 'zones.compactH', vars: { h: 2 } })
    expect(compactSinceLabel({ h: 1, m: 50 })).toEqual({ key: 'zones.compactH', vars: { h: 2 } })
  })

  it('says nothing when there is no transition to measure from', () => {
    expect(compactSinceLabel(null)).toBeNull()
  })
})

describe('zoneFitBounds', () => {
  const square = (
    lat: number,
    lon: number,
  ): {
    name_uk: string
    oblast: string
    region: Region
    geojson: GeoJSON.Polygon
  } => ({
    name_uk: 'x',
    region: 'kyiv',
    oblast: 'y',
    geojson: {
      type: 'Polygon',
      // [lon, lat] — GeoJSON order, the opposite of what the result must be in.
      coordinates: [
        [
          [lon, lat],
          [lon + 1, lat],
          [lon + 1, lat + 1],
          [lon, lat + 1],
          [lon, lat],
        ],
      ],
    },
  })

  const geometry = { a: square(50, 30), b: square(52, 32) }

  it('frames only the raions under alert', () => {
    const bounds = zoneFitBounds(geometry, {
      a: zone({ zone_id: 'a', alert: true }),
      b: zone({ zone_id: 'b', alert: false }),
    })
    expect(bounds).toEqual([
      [50, 30],
      [51, 31],
    ])
  })

  it('falls back to the whole watched area when nothing is sounding', () => {
    const bounds = zoneFitBounds(geometry, {
      a: zone({ zone_id: 'a' }),
      b: zone({ zone_id: 'b' }),
    })
    expect(bounds).toEqual([
      [50, 30],
      [53, 33],
    ])
  })

  it('ignores a zone whose siren state is stale — we do not know it is lit', () => {
    const bounds = zoneFitBounds(geometry, {
      a: zone({ zone_id: 'a', alert: true, stale: true }),
      b: zone({ zone_id: 'b', alert: true }),
    })
    expect(bounds).toEqual([
      [52, 32],
      [53, 33],
    ])
  })

  it('reads a MultiPolygon, not just a Polygon', () => {
    const multi = {
      m: {
        name_uk: 'x',
        oblast: 'y',
        region: 'kyiv' as Region,
        geojson: {
          type: 'MultiPolygon' as const,
          coordinates: [square(50, 30).geojson.coordinates, square(52, 32).geojson.coordinates],
        },
      },
    }
    expect(zoneFitBounds(multi, { m: zone({ zone_id: 'm', alert: true }) })).toEqual([
      [50, 30],
      [53, 33],
    ])
  })

  it('says nothing when the polygons have not loaded yet', () => {
    expect(zoneFitBounds({}, {})).toBeNull()
  })
})


describe('inShownRegions', () => {
  const shown = new Set<Region>(['sumy'])

  it("drops another oblast's raions", () => {
    const zones = {
      a: zone({ zone_id: 'a', region: 'kyiv' }),
      b: zone({ zone_id: 'b', region: 'sumy' }),
    }
    expect(Object.keys(inShownRegions(zones, shown))).toEqual(['b'])
  })

  it('keeps every followed region, not just the primary one', () => {
    const zones = {
      a: zone({ zone_id: 'a', region: 'kyiv' }),
      b: zone({ zone_id: 'b', region: 'sumy' }),
    }
    const both = new Set<Region>(['sumy', 'kyiv'])
    expect(Object.keys(inShownRegions(zones, both)).sort()).toEqual(['a', 'b'])
  })

  it('shows nothing rather than everything when no region is followed', () => {
    // The layer paints four oblasts; an empty set must not fall back to "all",
    // or the narrowing would silently stop applying.
    expect(inShownRegions({ a: zone({ zone_id: 'a' }) }, new Set<Region>())).toEqual({})
  })
})
