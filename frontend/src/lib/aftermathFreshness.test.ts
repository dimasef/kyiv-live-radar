import { describe, expect, it } from 'vitest'

import type { Aftermath } from '@/types'

import { fadeFactor, minutesSince } from './aftermathFreshness'

const HOUR = 60 * 60 * 1000
const NOW = Date.parse('2026-07-08T20:00:00Z')

function report(reportedAt: string): Aftermath {
  return {
    id: 1,
    district_id: 1,
    district_name: 'Дарницький',
    lat: 50.4,
    lon: 30.6,
    region: 'kyiv',
    reported_at: reportedAt,
    categories: ['fire'],
    text: 'Пожежа після удару',
    source_id: null,
    source_name: null,
  }
}

describe('aftermath fade', () => {
  it('holds full brightness through the first hour', () => {
    expect(fadeFactor(report('2026-07-08T20:00:00Z'), NOW)).toBe(1)
    expect(fadeFactor(report('2026-07-08T19:05:00Z'), NOW)).toBe(1)
  })

  it('dims with age and never disappears', () => {
    const sixHours = fadeFactor(report('2026-07-08T14:00:00Z'), NOW)
    const yesterday = fadeFactor(report('2026-07-07T20:00:00Z'), NOW)
    expect(sixHours).toBeLessThan(1)
    expect(yesterday).toBeLessThan(sixHours)
    // A floor, not zero: an old report is still a real thing that happened, and
    // an invisible marker is one nobody can click to find out why.
    expect(yesterday).toBeGreaterThanOrEqual(0.3)
  })

  it('keeps the floor for anything older than the window', () => {
    // The route never serves these, but a cached payload can outlive the
    // window — the ramp must not go negative when it does.
    expect(fadeFactor(report('2026-07-01T20:00:00Z'), NOW)).toBe(0.3)
  })

  it('reads a zone-less timestamp as UTC, not local time', () => {
    // One missing 'Z' shifts every age by the viewer's offset — a Kyiv client
    // once showed "186 хв тому" for a 6-minute-old sighting (+3 h).
    expect(minutesSince(report('2026-07-08T19:30:00'), NOW)).toBe(30)
    expect(minutesSince(report('2026-07-08T19:30:00Z'), NOW)).toBe(30)
  })

  it('never reports a negative age for a clock ahead of ours', () => {
    expect(minutesSince(report('2026-07-08T20:05:00Z'), NOW)).toBe(0)
    expect(fadeFactor(report('2026-07-08T20:05:00Z'), NOW)).toBe(1)
  })

  it('survives a missing timestamp instead of rendering NaN opacity', () => {
    const broken = { ...report('2026-07-08T20:00:00Z'), reported_at: '' }
    expect(fadeFactor(broken, NOW)).toBe(1)
    expect(minutesSince(broken, NOW)).toBe(0)
  })
})

describe('aftermath age in words', () => {
  it('counts whole minutes, then whole hours', () => {
    expect(minutesSince(report('2026-07-08T19:59:10Z'), NOW)).toBe(0)
    expect(minutesSince(report('2026-07-08T18:00:00Z'), NOW)).toBe(120)
    expect(minutesSince(report(new Date(NOW - 3 * HOUR).toISOString()), NOW)).toBe(180)
  })
})
