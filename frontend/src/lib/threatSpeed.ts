import type { TargetType, Threat } from '@/types'

/** Typical cruising speed of a target CLASS, in km/h. */
export interface SpeedRange {
  min: number
  max: number
}

/** Speed by target class — a reference figure, never a measurement of THIS
 * target.
 *
 * Measuring would be the obvious thing and it is the wrong thing: every
 * position we have is a district centroid, so two sightings a few kilometres
 * apart with a minute of ingestion jitter between them yield anything from 40 to
 * 900 km/h. A class figure is honestly approximate instead of precisely wrong —
 * which is also why every reading built on it is a range, prefixed with "~", and
 * carries the "not a measurement" hint.
 *
 * `unknown` gets nothing: a range spanning a drone and a ballistic missile
 * would say less than silence. */
export const TYPE_SPEED_KMH: Record<TargetType, SpeedRange | null> = {
  shahed: { min: 150, max: 200 },
  jet_drone: { min: 350, max: 600 },
  // An operator flies it by video link; cruise speed is what the airframe and
  // the link allow, not what a warhead needs.
  fpv: { min: 100, max: 150 },
  missile: { min: 700, max: 900 },
  ballistic: { min: 1500, max: 3000 },
  unknown: null,
}

/** The speed range to show for a target, or null when showing one would lie.
 *
 * A downed, lost or closed track isn't flying any more, and an impact is a
 * place — "~150–200 км/год" next to either reads as a live target still in the
 * air, which is exactly the wrong thing to tell someone. */
export function speedRangeOf(threat: Threat): SpeedRange | null {
  if (threat.closed_at != null || threat.kind === 'impact') return null
  if (threat.status === 'destroyed' || threat.status === 'lost' || threat.status === 'dismissed') {
    return null
  }
  return TYPE_SPEED_KMH[threat.target_type]
}

/** Whole minutes to cover `km` at each end of the range. The FASTER end gives
 * the shorter time, so `min` is computed from `range.max`.
 *
 * A sub-minute result stays 0 rather than rounding to 1 — the caller renders
 * that as "менш ніж 1 хв", which is the truth for a ballistic already overhead
 * and shouldn't be dressed up as a countdown. */
export function etaMinutes(km: number, range: SpeedRange): { min: number; max: number } {
  return {
    min: Math.round((km / range.max) * 60),
    max: Math.round((km / range.min) * 60),
  }
}

/** "5" when both ends agree, "4–6" when they don't — an en dash, matching how
 * the app writes every other range. */
export function formatRange(min: number, max: number): string {
  return min === max ? String(min) : `${min}–${max}`
}
