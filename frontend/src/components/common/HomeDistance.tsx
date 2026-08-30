import { Navigation } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { formatKm } from '@/lib/geo'
import { homeDistanceOf } from '@/lib/homeDistance'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

/** "~4.2 км від дому · наближається" — the number a person actually wants from
 * a target they just opened, with an arrow pointing from home toward it.
 *
 * Deliberately fuzzy: the "~" and the coarse rounding are there because every
 * sighting is a district centroid. Renders nothing when no home is set, or
 * when the threat has no position to measure from.
 *
 * Measures the TRACK — its latest sighting cluster — which is what the popup
 * asks: where is this target now. A feed row asks something else (how far was
 * the place this callout named), and has its own component for it,
 * feed/ThreatLog/SightingDistance. */
export default function HomeDistance({
  threat,
  className = '',
}: {
  threat: Threat
  className?: string
}) {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  if (home == null) return null

  const distance = homeDistanceOf(threat, home)
  if (distance == null) return null

  const tone = distance.nearHome
    ? 'text-red-400'
    : distance.trend === 'closing'
      ? 'text-amber-400'
      : 'text-slate-400'

  // Font size comes from the caller: the same line sits in a dense feed row and
  // in the roomier map popup, and one size can't serve both.
  return (
    <span
      title={t('home.approxHint')}
      className={`flex items-center gap-1 font-mono ${tone} ${className}`}
    >
      <Navigation
        size={10}
        className="flex-none"
        style={{ transform: `rotate(${distance.bearingFromHome}deg)` }}
        fill="currentColor"
      />
      ~{formatKm(distance.km)} {t('home.km')} {t('home.fromHome')}
      {distance.trend && (
        <span>· {distance.trend === 'closing' ? t('home.closing') : t('home.receding')}</span>
      )}
    </span>
  )
}
