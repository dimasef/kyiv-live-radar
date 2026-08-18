import { STATUS_CHIP_COLOR, STATUS_COLORS } from './theme'
import type { ClosedReason, Threat, ThreatStatus } from './types'

/** Label key per track status.
 *
 * A Record rather than a `status.${x}` template with a fallback, so a status
 * without a translation is a BUILD error instead of raw English in the UI —
 * which is exactly what shipped: only `status.impact` was ever translated, so a
 * destroyed target's popup read "destroyed" to a Ukrainian viewer. TypeScript
 * enforces that every status appears here, and locales/keys.test.ts enforces
 * that every key here exists in both bundles.
 */
export const STATUS_LABEL_KEY: Record<ThreatStatus, string> = {
  unconfirmed: 'status.unconfirmed',
  tracking: 'status.tracking',
  destroyed: 'status.destroyed',
  lost: 'status.lost',
  impact: 'status.impact',
  dismissed: 'status.dismissed',
}

/** Why a track closed, where that is more specific than `status` can be.
 *
 * `status='lost'` collapses three different endings — an official відбій, a
 * spotter's «дорозвідка» stand-down, and a silence timeout — so a chip driven by
 * status alone has to call all three "втрачено". Only `all_clear` is genuinely
 * different news (someone declared it over), so it gets its own label and the
 * all-clear green; the other two stay the honest neutral "nobody knows". */
const CLOSED_REASON_OVERRIDE: Partial<Record<ClosedReason, { labelKey: string; color: string }>> = {
  all_clear: { labelKey: 'status.allClear', color: STATUS_COLORS.clear },
}

export interface ThreatChip {
  labelKey: string
  color: string
}

/** The one lifecycle chip for a track — the map popup and the feed card must
 * never disagree about the same target, which they did: the feed said grey
 * «ЗНИЩЕНО» while the popup said green «ЗБИТО» for one shot-down drone. Both now
 * read this. */
export function threatChip(threat: Threat): ThreatChip {
  if (threat.status !== 'impact' && threat.closed_at && threat.closed_reason) {
    const override = CLOSED_REASON_OVERRIDE[threat.closed_reason]
    if (override) return override
  }
  return {
    labelKey: STATUS_LABEL_KEY[threat.status],
    color: STATUS_CHIP_COLOR[threat.status],
  }
}
