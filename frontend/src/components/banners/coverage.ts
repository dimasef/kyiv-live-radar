import type { Alert, Region } from '@/types'

/** Where the reader is, at the two granularities an alert can be about. */
export interface AlertScopeCtx {
  /** The raion the home point falls in (GET /alert-zones/at), null with no home
   * or a home outside every watched raion. */
  zoneId: string | null
  /** The oblast the reader follows, null only before the catalogue lands and
   * with no explicit choice. */
  region: Region | null
}

/** Whether an alert is about where the reader actually is.
 *
 * The bug this exists for: the banner used to ask only "same region?", and
 * region `kyiv` covers м. Київ AND the whole oblast around it. Someone in
 * Броварський район therefore saw Kyiv city's siren as their own, while their
 * own raion's siren — which the app did not store at all — showed nothing.
 *
 * With no home to place the reader (`zoneId === null`) this stays at the
 * oblast granularity it had before, minus raion alerts: a Kyiv reader who has
 * not marked a home must not get a full-width red banner because a siren went
 * off in Бучанський район 40 km away.
 */
export function alertCoversMe(alert: Alert, ctx: AlertScopeCtx): boolean {
  // Nothing to narrow to yet — fail towards showing the alert, the only safe
  // direction on this screen (same reasoning as status.ts::inFollowedRegion).
  if (ctx.region !== null && alert.region !== ctx.region) return false
  if (alert.zone_id != null) return alert.zone_id === ctx.zoneId
  // The official channel's announcements name no raion. An oblast-wide one
  // covers everyone in the region; a city one covers only the city.
  return alert.scope === 'oblast' || ctx.zoneId === null || ctx.zoneId === 'kyiv-city'
}

/** The alert the banner speaks about, out of the ones that cover the reader.
 *
 * The official channel wins when both apply: for Kyiv city it is the same siren
 * reported sooner and more reliably, which is why the district provider is not
 * allowed to write a `kyiv-city` alert at all.
 */
export function primaryAlert(alerts: Alert[]): Alert | null {
  const open = alerts.filter((a) => !a.ended_at)
  return open.find((a) => a.zone_id == null) ?? open[0] ?? null
}
