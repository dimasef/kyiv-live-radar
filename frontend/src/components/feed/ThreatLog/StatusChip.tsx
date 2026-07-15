import { Crosshair } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { STATUS_COLORS } from '@/theme'
import type { Threat } from '@/types'

// Closed-track feed label — driven by closed_reason (the explicit domain
// reason), not inferred from status/target_type. 'stand_down' (дорозвідка)
// and 'stale' (silence timeout) both read as "lost" — same collapse the
// legacy `status='lost'` value used before closed_reason existed.
const CLOSED_REASON_LABEL: Record<string, string> = {
  destroyed: 'log.closedReason.destroyed',
  all_clear: 'log.closedReason.allClear',
  stand_down: 'log.closedReason.lost',
  stale: 'log.closedReason.lost',
}
const CLOSED_REASON_COLOR: Record<string, string> = {
  destroyed: STATUS_COLORS.destroyed,
  all_clear: STATUS_COLORS.clear,
  stand_down: STATUS_COLORS.destroyed,
  stale: STATUS_COLORS.destroyed,
}

/** The "impact" / "destroyed" / "lost" pill shown next to a threat card's
 * type glyph — impact wins over a closed-reason (impact tracks close on
 * creation but read as a hit, not a loss). */
export default function StatusChip({ threat }: { threat: Threat }) {
  const { t } = useTranslation()

  if (threat.status === 'impact') {
    return (
      <span
        className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
        style={{ color: STATUS_COLORS.impact, background: `${STATUS_COLORS.impact}1a` }}
      >
        <Crosshair size={10} className="flex-none" />
        {t('log.impact')}
      </span>
    )
  }

  if (threat.closed_at && threat.closed_reason) {
    const color = CLOSED_REASON_COLOR[threat.closed_reason]
    return (
      <span
        className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
        style={{ color, background: `${color}1a` }}
      >
        {t(CLOSED_REASON_LABEL[threat.closed_reason])}
      </span>
    )
  }

  return null
}
