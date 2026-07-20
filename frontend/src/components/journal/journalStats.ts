import type { JournalDay, TargetType } from '@/types'

const TYPE_ORDER: TargetType[] = ['ballistic', 'missile', 'jet_drone', 'shahed', 'unknown']

/** Composite "how heavy was this day" score — the intensity encoding for the
 * calendar. Weights (owned here, the single place to tune; the backend returns
 * only raw counts): each inbound target counts 1, a confirmed strike 3 extra, a
 * ballistic target 5 extra, and each hour under city alert adds 1. */
export function intensityScore(d: JournalDay): number {
  const ballistic = d.type_counts.ballistic ?? 0
  const alertHours = d.alert_seconds / 3600
  return d.target_count + d.impact_count * 3 + ballistic * 5 + alertHours
}

/** Whether a day had any activity at all — distinguishes "quiet day" (bucket 1)
 * from "no data" (bucket 0), which a score of 0 alone can't. */
export function hasActivity(d: JournalDay): boolean {
  return (
    d.attack_count > 0 ||
    d.target_count > 0 ||
    d.impact_count > 0 ||
    d.alert_count > 0 ||
    d.district_count > 0
  )
}

export type IntensityBucket = 0 | 1 | 2 | 3 | 4

/** Absolute score thresholds for buckets 1–4, calibrated against real data
 * (a light night ≈ 2–16, a busy one ≈ 30–60, the 07-19 mass ballistic attack
 * ≈ 380). Absolute — not relative to the visible month — so a heavy day looks
 * equally alarming in any month and quiet months don't show fake-red days. */
const BUCKET_THRESHOLDS = [25, 80, 200] as const

/** Map a day to a 0–4 intensity bucket on the absolute scale. A day WITHOUT a
 * city air-raid alert renders as a PLAIN day (bucket 0, no fill), whatever the
 * spotter volume — no siren means it was never a real threat to Kyiv. Only
 * alert days get onto the yellow→red scale. */
export function intensityBucket(d: JournalDay): IntensityBucket {
  if (d.alert_count === 0) return 0
  const score = intensityScore(d)
  if (score <= BUCKET_THRESHOLDS[0]) return 1
  if (score <= BUCKET_THRESHOLDS[1]) return 2
  if (score <= BUCKET_THRESHOLDS[2]) return 3
  return 4
}

/** Calm→alarm "fire danger" ramp: no-data → light yellow → yellow → light red
 * → deepest red (the most dangerous day is the most red). SOLID colors only —
 * alpha-blended yellow over the ink background reads muddy brown. Validated:
 * worst adjacent-pair ΔE 26 incl. color-blind simulations, all steps ≥3:1
 * against the panel surface. */
export const INTENSITY_BG: readonly string[] = [
  'rgba(148,163,184,0.06)',
  '#fde68a',
  '#eab308',
  '#f87171',
  '#dc2626',
]

/** Buckets bright enough to need dark text on top. */
export const INTENSITY_DARK_TEXT: readonly boolean[] = [false, true, true, true, false]

export interface MonthSummary {
  attacks: number
  targets: number
  alertSeconds: number
  alertIncomplete: boolean
  activeDays: number
  /** The month's heaviest day by intensity score; null for an all-quiet month. */
  heaviestDate: string | null
}

/** Month-at-a-glance totals for the strip above the calendar. */
export function monthSummary(days: JournalDay[]): MonthSummary {
  let heaviest: JournalDay | null = null
  let heaviestScore = 0
  const sum = { attacks: 0, targets: 0, alertSeconds: 0, alertIncomplete: false, activeDays: 0 }
  for (const d of days) {
    if (!hasActivity(d)) continue
    sum.activeDays += 1
    sum.attacks += d.attack_count
    sum.targets += d.target_count + d.impact_count
    sum.alertSeconds += d.alert_seconds
    sum.alertIncomplete ||= d.alert_incomplete
    const score = intensityScore(d)
    if (score > heaviestScore) {
      heaviestScore = score
      heaviest = d
    }
  }
  return { ...sum, heaviestDate: heaviest?.date ?? null }
}

/** Type-count segments for the day's stacked breakdown bar, severest first,
 * zero-count types dropped. */
export function typeSegments(d: JournalDay): { type: TargetType; count: number }[] {
  return TYPE_ORDER.map((type) => ({ type, count: d.type_counts[type] ?? 0 })).filter(
    (s) => s.count > 0,
  )
}

/** Monday-first calendar cells for a month; null = a leading/trailing blank so
 * every week is 7 wide. Date strings are built from the y/m/d parts (never
 * toISOString) so there is no timezone shift. */
export function monthGrid(year: number, month0: number): (string | null)[] {
  const first = new Date(year, month0, 1)
  const daysIn = new Date(year, month0 + 1, 0).getDate()
  const leading = (first.getDay() + 6) % 7 // JS Sun=0 -> Monday-first offset
  const cells: (string | null)[] = Array(leading).fill(null)
  const m = String(month0 + 1).padStart(2, '0')
  for (let day = 1; day <= daysIn; day++) {
    cells.push(`${year}-${m}-${String(day).padStart(2, '0')}`)
  }
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

/** `from`/`to` ISO day bounds covering the whole month, for the API request. */
export function monthRange(year: number, month0: number): { from: string; to: string } {
  const daysIn = new Date(year, month0 + 1, 0).getDate()
  const m = String(month0 + 1).padStart(2, '0')
  return { from: `${year}-${m}-01`, to: `${year}-${m}-${String(daysIn).padStart(2, '0')}` }
}

export function todayISO(): string {
  const n = new Date()
  const m = String(n.getMonth() + 1).padStart(2, '0')
  const d = String(n.getDate()).padStart(2, '0')
  return `${n.getFullYear()}-${m}-${d}`
}

/** Localized "Липень 2026" heading. */
export function monthLabel(year: number, month0: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(
    new Date(year, month0, 1),
  )
}

/** Monday-first short weekday names (2024-01-01 is a Monday). */
export function weekdayLabels(locale: string): string[] {
  const fmt = new Intl.DateTimeFormat(locale, { weekday: 'short' })
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)))
}

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h && m) return `${h}г ${m}хв`
  if (h) return `${h}г`
  return `${m}хв`
}
