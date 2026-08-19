import { useTranslation } from 'react-i18next'

import { isQuiet, minutesSinceSeen } from '@/lib/threatFreshness'
import { useRadar } from '@/store'
import { CorroborationLine } from '@/threatDisplay'
import type { Threat } from '@/types'

import PopupSection from './PopupSection'
import { row } from './popupStyles'

/** How much this target is worth believing: who reported it, how confident the
 * fusion is, how old that is, and whether the sources contradict each other. */
export default function DataSection({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const now = useRadar((s) => s.nowMs + s.clockSkewMs)

  return (
    <PopupSection label={t('popup.data')}>
      <CorroborationLine threat={threat} as="div" style={row} />
      {/* Names the reason a target looks faded — "seen 14 min ago" is the fade
          in words, and the number is what an operator actually acts on. */}
      {isQuiet(threat, now) && (
        <div style={{ ...row, opacity: 0.6 }}>
          {t('threat.lastSeen', { n: minutesSinceSeen(threat, now) })}
        </div>
      )}
      {threat.has_conflict && (
        <div style={{ ...row, color: '#fb923c', fontWeight: 600, opacity: 1 }}>
          ⚠ {t('log.conflict')}
        </div>
      )}
    </PopupSection>
  )
}
