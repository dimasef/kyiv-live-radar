import type { Aftermath } from '@/types'

/** How old an aftermath report is, and how much that should dim its marker.
 *
 * Separate from `threatFreshness` on purpose, because the question is a
 * different one. A target fades because it has probably MOVED — its window is
 * the server's own `stale_at`, minutes wide, and past it the thing is gone. A
 * burnt-out building has not moved anywhere; what ages is the report's claim on
 * the reader's attention. Measured on the real corpus, a raion's reports run
 * from minutes after the strike to four days later («вже 4 день триває
 * ліквідація»), and the layer showed them identically.
 *
 * This replaces what the plan first reached for — a `retrospective` flag driven
 * by the six phrases in `_RETROSPECTIVE`. That vocabulary caught 1 of 25 real
 * reports, so a dashed outline would have marked 4% of the cases it was drawn
 * for while «уряд виділить 3,04 млрд грн на відновлення Вишневого» sat there
 * looking like something happening now. Age answers it without a word list.
 */

/** Full brightness for the first hour: a report from the raid still running is
 * not "old news", and fading from t=0 would make the whole layer look stale. */
const FRESH_MS = 60 * 60 * 1000

/** Mirrors the backend's `consequence_layer_hours` — the window the route
 * serves at all, so a marker reaches the floor exactly as it ages out of the
 * next refresh. Duplicated only as a fade ramp: nothing here decides what is
 * served, and if the setting changes the ramp is cosmetically off, never wrong.
 */
const WINDOW_MS = 24 * 60 * 60 * 1000

/** Floor, never 0: an old report is still a real thing that happened, and a
 * marker the reader can't see is one they can't click to find out why. */
const MIN_FADE = 0.3

const HAS_ZONE = /(?:Z|z|[+-]\d{2}:?\d{2})$/

/** Same rule as threatFreshness.parseUtc: a zone-less timestamp is UTC, not
 * local. One missing 'Z' shifts every age by the viewer's offset. */
function parseUtc(iso: string | null | undefined): number {
  if (!iso) return NaN
  return Date.parse(HAS_ZONE.test(iso) ? iso : `${iso}Z`)
}

export function ageMs(report: Aftermath, now: number): number {
  const at = parseUtc(report.reported_at)
  if (Number.isNaN(at)) return 0
  return Math.max(0, now - at)
}

/** 1 while fresh, ramping down to MIN_FADE across the layer's window. */
export function fadeFactor(report: Aftermath, now: number): number {
  const age = ageMs(report, now)
  if (age <= FRESH_MS) return 1
  const ramp = (age - FRESH_MS) / (WINDOW_MS - FRESH_MS)
  return Math.max(MIN_FADE, 1 - ramp * (1 - MIN_FADE))
}

/** Whole hours since the report, for the popup. Minutes below an hour, because
 * "0 год" is not an answer. */
export function minutesSince(report: Aftermath, now: number): number {
  return Math.floor(ageMs(report, now) / 60000)
}
