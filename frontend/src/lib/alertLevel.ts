import { STATUS_COLORS } from '@/theme'
import type { Alert } from '@/types'

/** The colour a threat level is spoken in — the same two the map paints raions
 * with (`ZONE_STYLES` in components/map/constants), so the banner, the feed and
 * the polygon can never disagree about what «жовтий» looks like.
 *
 * An ungraded alert takes the red. Everything downstream treats 'unknown' as a
 * floor rather than a third state: it is what every alert before 06.09.2026 and
 * every channel outside Kyiv carries, and understating a siren is the one
 * mistake this app must not make. What changes is the WORDS — see
 * `alertThreatKey`, which never names a threat nobody reported. */
export const ALERT_LEVEL_COLORS = {
  yellow: '#f59e0b',
  red: STATUS_COLORS.confirmed,
  unknown: STATUS_COLORS.confirmed,
} as const

export function alertLevelColor(alert: Pick<Alert, 'level'>): string {
  return ALERT_LEVEL_COLORS[alert.level] ?? ALERT_LEVEL_COLORS.unknown
}

/** What to call this alert: the official name of the threat it announced, or
 * the plain «Повітряна тривога» when nothing graded it. */
export function alertThreatKey(alert: Pick<Alert, 'threat'>): string {
  return `alert.threat.${alert.threat}`
}
