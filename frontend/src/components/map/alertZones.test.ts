import { describe, expect, it } from 'vitest'

import type { Alert, AlertZone, Region } from '@/types'

import {
  alertedZones,
  compactSinceLabel,
  inShownRegions,
  sinceParts,
  withOfficialKyiv,
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

describe('withOfficialKyiv', () => {
  const KYIV = 'kyiv-city'

  const city = (over: Partial<AlertZone> = {}) =>
    zone({ zone_id: KYIV, name_uk: 'м. Київ', oblast: 'м. Київ', ...over })

  const alert = (over: Partial<Alert> = {}): Alert =>
    ({
      id: 1,
      region: 'kyiv',
      scope: 'city',
      zone_id: null,
      alert_type: 'air_raid',
      started_at: '2026-09-02T20:00:00Z',
      ended_at: null,
      provider: 'telegram',
      closed_reason: null,
      ...over,
    }) as Alert

  it('lights the city from an open official alert, with its own start time', () => {
    // The disagreement this removes: the banner reads the official channel and
    // the polygon read the district provider, so the map could sit dark while
    // the banner screamed.
    const out = withOfficialKyiv({ [KYIV]: city({ alert: false }) }, [alert()], true)
    expect(out[KYIV].alert).toBe(true)
    expect(out[KYIV].changed_at).toBe('2026-09-02T20:00:00Z')
  })

  it('clears the city when the provider still believes in a siren', () => {
    const provider = city({ alert: true, changed_at: '2026-09-02T19:00:00Z' })
    const out = withOfficialKyiv({ [KYIV]: provider }, [], true)
    expect(out[KYIV].alert).toBe(false)
  })

  it('counts a quiet city from the last відбій', () => {
    const done = alert({ ended_at: '2026-09-02T21:30:00Z', closed_reason: 'official' })
    expect(withOfficialKyiv({ [KYIV]: city() }, [done], true)[KYIV].changed_at).toBe(
      '2026-09-02T21:30:00Z',
    )
  })

  it('goes stale, never clear, when the listener is down', () => {
    // An outage rendered as «відбій» is the one failure this whole layer is
    // engineered against — and now Kyiv has only one source to lose.
    const out = withOfficialKyiv({ [KYIV]: city({ alert: true }) }, [], false)
    expect(zoneTone(out[KYIV])).toBe('stale')
  })

  it('leaves the provider alone when there is no Telegram feed at all', () => {
    // Simulator / replay / a dev box: nothing better to prefer, and blanking
    // the capital on every dev run would be a worse lie than the disagreement.
    const provider = { [KYIV]: city({ alert: true, changed_at: '2026-09-02T19:00:00Z' }) }
    expect(withOfficialKyiv(provider, [], null)).toEqual(provider)
  })

  it('never touches any other raion', () => {
    const zones = { [KYIV]: city(), other: zone({ zone_id: 'other', alert: true }) }
    expect(withOfficialKyiv(zones, [alert()], true).other).toEqual(zones.other)
  })

  it('ignores a raion alert and another region\'s city alert', () => {
    const raion = alert({ id: 2, scope: 'raion', zone_id: 'kyiv-obl-brovarskyi' })
    const sumy = alert({ id: 3, region: 'sumy' })
    expect(withOfficialKyiv({ [KYIV]: city() }, [raion, sumy], true)[KYIV].alert).toBe(false)
  })
})
