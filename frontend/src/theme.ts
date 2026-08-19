import type { TargetType, Threat, ThreatStatus } from './types'

export const STATUS_COLORS = {
  confirmed: '#ef4444',
  unconfirmed: '#eab308',
  destroyed: '#6b7280',
  clear: '#22c55e',
  conflict: '#f97316',
  impact: '#d946ef',
  /** Nobody is reporting this target any more — a state, not an outcome. Blue
   * because it must not read as either alarm or all-clear, and grey (which it
   * used to be) read as "resolved, ignore it" for a target that may well still
   * be flying. Same sky hue as HOME_COLOR, deliberately: the two never appear as
   * peers (one labels a place, the other a track's state), and one blue in the
   * palette beats two that differ just enough to look like a mistake. */
  unseen: '#38bdf8',
} as const

/** Chip colour per track status (the popup's lifecycle chip), all from the
 * shared palette rather than new hues.
 *
 * The scale is by OUTCOME, not by "is it still open": live is the confirmed red,
 * a hedged report the unconfirmed yellow, and a shot-down target the same GREEN
 * the all-clear uses — a downed target is good news, and grey would read as
 * merely "gone". A target nobody is reporting any more (`lost` — «не фіксується»)
 * gets the blue: its fate is unknown, which is neither good news nor bad. An
 * impact keeps its own magenta, matching the feed.
 */
export const STATUS_CHIP_COLOR: Record<ThreatStatus, string> = {
  tracking: STATUS_COLORS.confirmed,
  unconfirmed: STATUS_COLORS.unconfirmed,
  destroyed: STATUS_COLORS.clear,
  lost: STATUS_COLORS.unseen,
  impact: STATUS_COLORS.impact,
  dismissed: STATUS_COLORS.destroyed,
}

/** The user's "home" marker/circle color — the map's home icon/circle, the
 * legend's home swatch, and the feed's non-clear info-notice accent. */
export const HOME_COLOR = '#38bdf8'

/** A friend's shared-home marker (see FriendLayer). Pink-400 — distinct from
 * own-home cyan and from every status/type hue in use; paired with a different
 * (person) marker shape so the two homes never read as the same thing. */
export const FRIEND_HOME_COLOR = '#f472b6'

/** Home-circle accent while a threat concerns the home zone (lib/homeDanger.ts):
 * a track on course toward home reuses the conflict orange, a target near home
 * (or ballistic on the home raion) the confirmed red. */
export const HOME_DANGER_COLORS = {
  warning: STATUS_COLORS.conflict,
  danger: STATUS_COLORS.confirmed,
} as const

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
