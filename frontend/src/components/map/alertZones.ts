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

/** Which i18n key and values render the always-on centre label's duration.
 *
 * One unit, never two: this sits over the map permanently on every raion, so it
 * gets "40хв" or "2г" where the hover caption can afford «1 год 20 хв». Under an
 * hour the minutes are the whole answer; past it they stop mattering — nobody
 * acts differently on a siren that has run 1:20 versus 1:35, and the extra
 * digits are two more characters to read past on thirteen labels at once.
 *
 * Rounded, not truncated: 1 h 50 min is "2г", because floor would call it "1г"
 * for the better part of an hour and read as newer than it is. */
export function compactSinceLabel(
  since: { h: number; m: number } | null,
): { key: 'zones.compactH' | 'zones.compactM'; vars: Record<string, number> } | null {
  if (!since) return null
  if (since.h > 0) {
    return { key: 'zones.compactH', vars: { h: since.h + (since.m >= 30 ? 1 : 0) } }
  }
  return { key: 'zones.compactM', vars: { m: since.m } }
}

/** Zones under alert, most recent first — what a "N raions under siren" summary
 * would read off. */
export function alertedZones(zones: Record<string, AlertZone>): AlertZone[] {
  return Object.values(zones)
    .filter((z) => z.alert && !z.stale)
    .sort((a, b) => (b.changed_at ?? '').localeCompare(a.changed_at ?? ''))
}
