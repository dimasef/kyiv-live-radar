import type { AnalyticsPeriod, StatsDay, TargetType } from '@/types'

import { TYPE_ORDER } from '../journalStats'

export const PERIODS: AnalyticsPeriod[] = ['30d', '90d', 'all']

/** A trend column: one day, or one Monday-started week. */
export interface TrendBucket {
  key: string // ISO date of the bucket's first day
  label: string
  targets: number
  segments: { type: TargetType; count: number }[]
}

/** Days become weekly columns past ~5 weeks — 90 daily columns on a phone are a
 * picket fence, not a trend. */
export function shouldGroupByWeek(days: StatsDay[]): boolean {
  return days.length > 35
}

function mondayOf(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${String(d.getDate()).padStart(2, '0')}`
}

function segmentsOf(typeCounts: Record<string, number>): TrendBucket['segments'] {
  return TYPE_ORDER.map((type) => ({ type, count: typeCounts[type] ?? 0 })).filter(
    (s) => s.count > 0,
  )
}

/** Group the period's days into trend columns, daily or weekly, oldest first. */
export function trendBuckets(days: StatsDay[], byWeek: boolean, locale: string): TrendBucket[] {
  const totals = new Map<string, Record<string, number>>()
  const targets = new Map<string, number>()
  for (const d of days) {
    const key = byWeek ? mondayOf(d.date) : d.date
    const bucket = totals.get(key) ?? {}
    for (const [type, count] of Object.entries(d.type_counts)) {
      bucket[type] = (bucket[type] ?? 0) + count
    }
    totals.set(key, bucket)
    targets.set(key, (targets.get(key) ?? 0) + d.target_count + d.impact_count)
  }
  const short = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' })
  return [...totals.keys()]
    .sort()
    .map((key) => ({
      key,
      label: short.format(new Date(`${key}T00:00:00`)),
      targets: targets.get(key) ?? 0,
      segments: segmentsOf(totals.get(key) ?? {}),
    }))
}

/** Type rows for the table twin, severest first, zero-count types dropped. */
export function typeRows(
  typeTotals: Record<string, number>,
  typeDays: Record<string, number>,
): { type: TargetType; count: number; share: number; days: number }[] {
  const total = Object.values(typeTotals).reduce((n, v) => n + v, 0)
  return TYPE_ORDER.map((type) => ({
    type,
    count: typeTotals[type] ?? 0,
    share: total ? (typeTotals[type] ?? 0) / total : 0,
    days: typeDays[type] ?? 0,
  })).filter((r) => r.count > 0)
}

/** Share of the whole period spent under a city alert (0..1), normalized on the
 * days the alert feed actually covered — not on the period length, which would
 * dilute it with days that had no alert source at all. */
export function alertTimeShare(alertSeconds: number, alertDaysObserved: number): number {
  return alertDaysObserved ? alertSeconds / (alertDaysObserved * 86400) : 0
}

export function formatPercent(share: number, digits = 0): string {
  return `${(share * 100).toFixed(digits)}%`
}

/** "5 год 20 хв" — compact and never zero-padded; hours-only past a day. */
export function formatHours(seconds: number): string {
  // Minutes first, then split — see journalStats.formatDuration for the "60хв"
  // this avoids.
  const total = Math.round(seconds / 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h >= 24) return `${h} год`
  if (h && m) return `${h} год ${m} хв`
  if (h) return `${h} год`
  return `${m} хв`
}

/** Two-digit hour label for the hour-of-day axis. */
export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, '0')}`
}
