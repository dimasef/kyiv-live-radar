import type { AlertZone } from '@/types'

/** How a zone should be painted. `stale` is its own tone on purpose: when the
 * provider is unreachable we know nothing, and drawing that as "відбій" would
 * turn an outage into a false all-clear. */
export type ZoneTone = 'alert' | 'clear' | 'stale'

export function zoneTone(zone: AlertZone): ZoneTone {
  if (zone.stale) return 'stale'
  return zone.alert ? 'alert' : 'clear'
}

/** How long the zone has held its current state, split into hours+minutes.
 * Null when the provider never reported a transition for it, or when its
 * timestamp is in the future (a clock disagreement — better to say nothing). */
export function sinceParts(
  changedAt: string | null | undefined,
  nowMs: number,
): { h: number; m: number } | null {
  if (!changedAt) return null
  const began = Date.parse(changedAt)
  if (Number.isNaN(began)) return null
  const minutes = Math.floor((nowMs - began) / 60_000)
  if (minutes < 0) return null
  return { h: Math.floor(minutes / 60), m: minutes % 60 }
}

/** Zones under alert, most recent first — what a "N raions under siren" summary
 * would read off. */
export function alertedZones(zones: Record<string, AlertZone>): AlertZone[] {
  return Object.values(zones)
    .filter((z) => z.alert && !z.stale)
    .sort((a, b) => (b.changed_at ?? '').localeCompare(a.changed_at ?? ''))
}
