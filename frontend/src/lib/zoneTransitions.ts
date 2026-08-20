import type { AlertZone } from '@/types'

/** Raions whose siren has just been called off — an all-clear that happened
 * while we were watching, not one we merely learned about.
 *
 * The map lights these green for a few seconds, so the rule is deliberately
 * narrow. The zone must have been under a live siren in the state we already
 * held, and must now be live-clear:
 *
 * - A zone seen for the first time never qualifies. On boot every raion arrives
 *   at once and most of them are quiet — flashing those would announce
 *   all-clears that may have ended hours ago, on every page load.
 * - Neither does a transition through `stale`. When the provider is unreachable
 *   we stop knowing anything; coming back with "clear" is news about the
 *   connection, not about the siren.
 */
export function allClearedZoneIds(
  held: Record<string, AlertZone>,
  incoming: AlertZone[],
): string[] {
  return incoming
    .filter((zone) => {
      const before = held[zone.zone_id]
      return before != null && before.alert && !before.stale && !zone.alert && !zone.stale
    })
    .map((zone) => zone.zone_id)
}
