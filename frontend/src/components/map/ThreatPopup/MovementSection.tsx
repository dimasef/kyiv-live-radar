import { useTranslation } from 'react-i18next'

import HomeDistance from '@/components/common/HomeDistance'
import { homeDistanceOf } from '@/lib/homeDistance'
import { etaMinutes, formatRange, speedRangeOf } from '@/lib/threatSpeed'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

import PopupSection from './PopupSection'
import { row } from './popupStyles'

/** How fast the class of target flies, how far it is from home, and — only for
 * one actually closing in — roughly how long that leaves.
 *
 * Every number here is approximate by construction (a class speed against a
 * district centroid), so all three lines carry a "~"/"≈" and a hint saying so.
 * Renders nothing when there is neither a speed nor a distance to state. */
export default function MovementSection({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  // Recomputed here even though HomeDistance does its own: the section needs to
  // know whether that line will appear at all. A cheap pure call beats threading
  // the result through a component the feed also uses.
  const distance = home ? homeDistanceOf(threat, home) : null
  const range = speedRangeOf(threat)
  if (range == null && distance == null) return null

  const eta = range && distance?.trend === 'closing' ? etaMinutes(distance.km, range) : null
  // Same tones as the HomeDistance line above it — the pair reads as one block.
  const tone = distance?.nearHome ? 'text-red-400' : 'text-amber-400'

  return (
    <PopupSection label={t('popup.movement')}>
      {range && (
        <div style={row} title={t('speed.approxHint')}>
          ~{range.min}–{range.max} {t('speed.kmh')}
        </div>
      )}
      <HomeDistance threat={threat} className="mt-0.5 text-[12px]" />
      {eta && (
        <div className={`mt-0.5 font-mono text-[12px] ${tone}`} title={t('speed.etaHint')}>
          {eta.max === 0
            ? t('speed.etaSoon')
            : // A 0 lower bound next to a 1 would read as "0–1 хв"; the floor is
              // the honest form of "already almost here".
              t('speed.eta', { v: formatRange(Math.max(1, eta.min), eta.max) })}
        </div>
      )}
    </PopupSection>
  )
}
