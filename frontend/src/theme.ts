import type { TargetType, Threat } from './types'

export const STATUS_COLORS = {
  confirmed: '#ef4444',
  destroyed: '#6b7280',
  clear: '#22c55e',
  conflict: '#f97316',
  impact: '#d946ef',
} as const

/** The user's "home" marker/circle color — the map's home icon/circle, the
 * legend's home swatch, and the feed's non-clear info-notice accent. */
export const HOME_COLOR = '#38bdf8'

/** StatusBanner's attack-severity accent: ballistic gets the same red as a
 * confirmed sighting; every other notable attack type gets the same orange
 * as a fusion conflict — reusing the shared palette rather than one-off hex. */
export const INCIDENT_SEVERITY_COLOR = {
  ballistic: STATUS_COLORS.confirmed,
  other: STATUS_COLORS.conflict,
} as const

/** Per-TYPE marker colour — the primary encoding on the map/feed: the colour
 * tells you WHAT the target is. Shape (threatIcons.ts) reinforces the same type.
 * (red is reserved for a future `hypersonic` type — Kinzhal is `ballistic` for now.) */
export const TYPE_COLORS: Record<TargetType, string> = {
  shahed: '#facc15', // yellow
  jet_drone: '#fb923c', // orange
  missile: '#f1f5f9', // white (cruise)
  ballistic: '#a855f7', // violet
  unknown: '#94a3b8', // neutral slate
}

/** A shot-down / lost track is greyed out regardless of type. */
export const MUTED_COLOR = STATUS_COLORS.destroyed

/** A threat's display colour: TYPE colour, greyed once it's destroyed/lost. An
 * impact keeps its type colour (the burst SHAPE marks the hit; see threatIcons).
 * Source conflict is no longer a colour — it shows as a dashed track + feed chip. */
export function threatColor(t: Threat): string {
  if (t.status === 'destroyed' || t.status === 'lost') return MUTED_COLOR
  return TYPE_COLORS[t.target_type] ?? TYPE_COLORS.unknown
}
