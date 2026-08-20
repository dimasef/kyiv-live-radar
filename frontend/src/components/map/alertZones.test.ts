import { describe, expect, it } from 'vitest'

import type { AlertZone } from '@/types'

import { alertedZones, compactSinceLabel, sinceParts, zoneTone } from './alertZones'

const zone = (over: Partial<AlertZone> = {}): AlertZone => ({
  zone_id: 'kyiv-obl-vyshhorodskyi',
  name_uk: 'Вишгородський район',
  oblast: 'Київська область',
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
