import { Crosshair } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { threatChip } from '@/threatLabels'
import type { Threat } from '@/types'

/** The lifecycle pill next to a threat card's type glyph.
 *
 * Label and colour come from `threatChip` — the SAME source the map popup uses,
 * so one target never reads green «ЗБИТО» on the map and grey «ЗНИЩЕНО» in the
 * feed. The feed shows it only once a track is off the board: a live card would
 * otherwise carry a chip on every single row, which is noise in a log where
 * "still flying" is the default. */
export default function StatusChip({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const isImpact = threat.status === 'impact'
  if (!isImpact && !(threat.closed_at && threat.closed_reason)) return null

  const { labelKey, color } = threatChip(threat)
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color, background: `${color}1a` }}
    >
      {isImpact && <Crosshair size={10} className="flex-none" />}
      {t(labelKey)}
    </span>
  )
}
