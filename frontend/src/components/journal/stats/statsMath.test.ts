import { describe, expect, it } from 'vitest'

import type { StatsDay } from '@/types'

import {
  alertTimeShare,
  formatHours,
  formatPercent,
  shouldGroupByWeek,
  trendBuckets,
  typeRows,
} from './statsMath'

function day(date: string, over: Partial<StatsDay> = {}): StatsDay {
  return {
    date,
    attack_count: 0,
    track_count: 0,
    target_count: 0,
    impact_count: 0,
    alert_count: 0,
    alert_seconds: 0,
    alert_incomplete: false,
    type_counts: {},
    ...over,
  }
}

describe('trendBuckets', () => {
  it('keeps one column per day when the span is short', () => {
    const days = [
      day('2026-08-10', { target_count: 2, type_counts: { shahed: 2 } }),
      day('2026-08-11', { target_count: 1, type_counts: { ballistic: 1 } }),
    ]
    const buckets = trendBuckets(days, false, 'uk-UA')
    expect(buckets.map((b) => b.key)).toEqual(['2026-08-10', '2026-08-11'])
    expect(buckets[0].segments).toEqual([{ type: 'shahed', count: 2 }])
  })

  it('folds days into Monday-started weeks, oldest first', () => {
    // 2026-08-10 is a Monday; the 16th is that week's Sunday, the 17th a new week.
    const days = [
      day('2026-08-10', { target_count: 1, type_counts: { shahed: 1 } }),
      day('2026-08-16', { target_count: 2, type_counts: { shahed: 1, ballistic: 1 } }),
      day('2026-08-17', { target_count: 3, type_counts: { ballistic: 3 } }),
    ]
    const buckets = trendBuckets(days, true, 'uk-UA')
    expect(buckets.map((b) => b.key)).toEqual(['2026-08-10', '2026-08-17'])
    expect(buckets[0].targets).toBe(3)
    // Severity-ordered, and the same type summed across the week.
    expect(buckets[0].segments).toEqual([
      { type: 'ballistic', count: 1 },
      { type: 'shahed', count: 2 },
    ])
    expect(buckets[1].targets).toBe(3)
  })

  it('counts impacts as targets in a column', () => {
    const days = [day('2026-08-10', { target_count: 1, impact_count: 2 })]
    expect(trendBuckets(days, false, 'uk-UA')[0].targets).toBe(3)
  })

  it('switches to weeks only past five weeks of columns', () => {
    const mk = (n: number) => Array.from({ length: n }, (_, i) => day(`2026-08-${i + 1}`))
    expect(shouldGroupByWeek(mk(30))).toBe(false)
    expect(shouldGroupByWeek(mk(35))).toBe(false)
    expect(shouldGroupByWeek(mk(36))).toBe(true)
  })
})

describe('typeRows', () => {
  it('drops empty types, orders by severity and shares sum to 1', () => {
    const rows = typeRows({ shahed: 3, ballistic: 1, missile: 0 }, { shahed: 2, ballistic: 1 })
    expect(rows.map((r) => r.type)).toEqual(['ballistic', 'shahed'])
    expect(rows[0].share).toBeCloseTo(0.25)
    expect(rows.reduce((n, r) => n + r.share, 0)).toBeCloseTo(1)
    expect(rows[1].days).toBe(2)
  })

  it('never divides by zero on an empty period', () => {
    expect(typeRows({}, {})).toEqual([])
  })
})

describe('alertTimeShare', () => {
  it('normalizes on the alert-coverage days, not the period length', () => {
    // 12 h of alerts over 5 covered days = 10% of that window.
    expect(alertTimeShare(12 * 3600, 5)).toBeCloseTo(0.1)
  })

  it('is zero when the alert feed covered nothing', () => {
    expect(alertTimeShare(3600, 0)).toBe(0)
  })
})

describe('formatting', () => {
  it('formats durations compactly', () => {
    expect(formatHours(0)).toBe('0 хв')
    expect(formatHours(90 * 60)).toBe('1 г 30 хв')
    expect(formatHours(2 * 3600)).toBe('2 г')
    expect(formatHours(40 * 3600)).toBe('40 г')
  })

  it('formats percents at the requested precision', () => {
    expect(formatPercent(0.1234)).toBe('12%')
    expect(formatPercent(0.1234, 1)).toBe('12.3%')
  })
})
