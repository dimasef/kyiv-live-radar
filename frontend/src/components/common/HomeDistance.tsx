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
 * `notableOnly` is the feed-list form: it appears ONLY for a target near home
 * or closing on it, and drops the "від дому" tail. Twenty identical numbers
 * down a busy feed would hide the one that matters, which is the opposite of
 * what this is for. */
export default function HomeDistance({
  threat,
  notableOnly = false,
  className = '',
}: {
  threat: Threat
  notableOnly?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  if (home == null) return null

  const distance = homeDistanceOf(threat, home)
  if (distance == null) return null

  const notable = distance.nearHome || distance.trend === 'closing'
  if (notableOnly && !notable) return null

  const tone = distance.nearHome
    ? 'text-red-400'
    : distance.trend === 'closing'
      ? 'text-amber-400'
      : 'text-slate-400'

  return (
    <span
      title={t('home.approxHint')}
      className={`flex items-center gap-1 font-mono text-[10px] ${tone} ${className}`}
    >
      <Navigation
        size={10}
        className="flex-none"
        style={{ transform: `rotate(${distance.bearingFromHome}deg)` }}
        fill="currentColor"
      />
      ~{formatKm(distance.km)} {t('home.km')}
      {!notableOnly && ` ${t('home.fromHome')}`}
      {!notableOnly && distance.trend && (
        <span>· {distance.trend === 'closing' ? t('home.closing') : t('home.receding')}</span>
      )}
    </span>
  )
}
