import { describe, expect, it } from 'vitest'

import type { JournalDay } from '@/types'

import {
  hasActivity,
  intensityBucket,
  intensityScore,
  monthGrid,
  monthRange,
  monthSummary,
  typeSegments,
} from './journalStats'

function day(over: Partial<JournalDay> = {}): JournalDay {
  return {
    date: '2026-07-19',
    attack_count: 0,
    track_count: 0,
    target_count: 0,
    impact_count: 0,
    type_counts: { shahed: 0, jet_drone: 0, missile: 0, ballistic: 0, unknown: 0 },
    alert_count: 0,
    alert_seconds: 0,
    longest_alert_seconds: 0,
    alert_incomplete: false,
    alert_windows: [],
    district_ids: [],
    district_count: 0,
    ...over,
  } as JournalDay
}

describe('intensityScore', () => {
  it('weights an impact 3x and a ballistic target 5x over a plain target', () => {
    expect(intensityScore(day({ target_count: 4 }))).toBe(4)
    expect(intensityScore(day({ target_count: 4, impact_count: 1 }))).toBe(7)
    expect(
      intensityScore(day({ target_count: 4, type_counts: { ...day().type_counts, ballistic: 2 } })),
    ).toBe(14)
  })

  it('adds one point per hour of city alert', () => {
    expect(intensityScore(day({ alert_seconds: 7200 }))).toBe(2)
  })
})

describe('hasActivity', () => {
  it('separates a genuinely quiet day from a no-data day', () => {
    expect(hasActivity(day())).toBe(false)
    // An alert with no targets at all is still activity — this is exactly the
    // case a score of 0 cannot distinguish on its own.
    expect(hasActivity(day({ alert_count: 1 }))).toBe(true)
  })
})

describe('intensityBucket', () => {
  it('renders a no-siren day as plain, however loud the spotters were', () => {
    expect(intensityBucket(day({ target_count: 500, alert_count: 0 }))).toBe(0)
  })

  it('climbs the scale only on alert days', () => {
    expect(intensityBucket(day({ alert_count: 1, target_count: 3 }))).toBe(1)
    expect(intensityBucket(day({ alert_count: 1, target_count: 50 }))).toBe(2)
    expect(intensityBucket(day({ alert_count: 1, target_count: 150 }))).toBe(3)
    expect(intensityBucket(day({ alert_count: 1, target_count: 400 }))).toBe(4)
  })

  it('puts each threshold value in the LOWER bucket (boundaries are inclusive)', () => {
    expect(intensityBucket(day({ alert_count: 1, target_count: 25 }))).toBe(1)
    expect(intensityBucket(day({ alert_count: 1, target_count: 26 }))).toBe(2)
  })
})

describe('monthSummary', () => {
  it('ignores empty days and counts impacts into the target total', () => {
    const s = monthSummary([
      day({ date: '2026-07-01', attack_count: 2, target_count: 10, impact_count: 1 }),
      day({ date: '2026-07-02' }),
      day({ date: '2026-07-03', attack_count: 1, target_count: 3, alert_count: 1 }),
    ])
    expect(s.activeDays).toBe(2)
    expect(s.attacks).toBe(3)
    expect(s.targets).toBe(14)
  })

  it('flags the month as incomplete if any single day was', () => {
    const s = monthSummary([day({ alert_count: 1, alert_incomplete: true })])
    expect(s.alertIncomplete).toBe(true)
  })

  it('names the heaviest day, and null for an all-quiet month', () => {
    const s = monthSummary([
      day({ date: '2026-07-01', target_count: 5 }),
      day({ date: '2026-07-02', target_count: 40 }),
    ])
    expect(s.heaviestDate).toBe('2026-07-02')
    expect(monthSummary([day(), day()]).heaviestDate).toBeNull()
  })
})

describe('typeSegments', () => {
  it('orders severest-first and drops zero counts', () => {
    const segs = typeSegments(
      day({ type_counts: { shahed: 3, jet_drone: 0, missile: 1, ballistic: 2, unknown: 0 } }),
    )
    expect(segs).toEqual([
      { type: 'ballistic', count: 2 },
      { type: 'missile', count: 1 },
      { type: 'shahed', count: 3 },
    ])
  })
})

describe('monthGrid', () => {
  it('always returns whole Monday-first weeks', () => {
    for (const m of [0, 1, 6, 11]) {
      const cells = monthGrid(2026, m)
      expect(cells.length % 7).toBe(0)
    }
  })

  it('pads a month starting mid-week with leading blanks', () => {
    // 2026-07-01 is a Wednesday -> two blanks before it.
    const cells = monthGrid(2026, 6)
    expect(cells.slice(0, 2)).toEqual([null, null])
    expect(cells[2]).toBe('2026-07-01')
  })

  it('builds dates from local parts, never a UTC-shifted toISOString', () => {
    expect(monthGrid(2026, 0).filter(Boolean)[0]).toBe('2026-01-01')
  })

  it('handles a leap February', () => {
    expect(monthGrid(2024, 1).filter(Boolean)).toHaveLength(29)
  })
})

describe('monthRange', () => {
  it('spans the whole month, zero-padded', () => {
    expect(monthRange(2026, 6)).toEqual({ from: '2026-07-01', to: '2026-07-31' })
    expect(monthRange(2026, 1)).toEqual({ from: '2026-02-01', to: '2026-02-28' })
  })
})
