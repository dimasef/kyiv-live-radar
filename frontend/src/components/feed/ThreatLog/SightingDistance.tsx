import { Navigation } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { formatKm } from '@/lib/geo'
import { sightingDistanceOf } from '@/lib/homeDistance'
import { useRadar } from '@/store'
import type { ThreatEvent } from '@/types'

/** "~4.2 км" on a feed row, with an arrow pointing from home toward the place
 * that row is about.
 *
 * Measures THIS sighting, not its track. The map popup's HomeDistance measures
 * the track, which is right there — the popup answers "where is this target
 * now" — but a feed row is a record of one callout, and reading the track's
 * current position onto it made every row of one track show the same number.
 *
 * Shown only for a sighting inside the home zone: twenty distances down a busy
 * feed hide the one that matters. The track's approach trend used to widen that
 * gate, and deliberately no longer does — it is a property of the track as of
 * NOW, so on an older row it was a claim about the wrong moment, and after a
 * page reload the feed carries no track events to derive it from at all.
 *
 * Deliberately fuzzy: every sighting is a district or landmark centroid, which
 * is what the "~" and the coarse rounding are admitting to.
 */
export default function SightingDistance({
  event,
  className = '',
}: {
  event: ThreatEvent
  className?: string
}) {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  if (home == null) return null

  const distance = sightingDistanceOf(event, home)
  if (distance == null || !distance.nearHome) return null

  return (
    <span
      title={t('home.approxHint')}
      className={`flex items-center gap-1 font-mono text-red-400 ${className}`}
    >
      <Navigation
        size={10}
        className="flex-none"
        style={{ transform: `rotate(${distance.bearingFromHome}deg)` }}
        fill="currentColor"
      />
      ~{formatKm(distance.km)} {t('home.km')}
    </span>
  )
}
