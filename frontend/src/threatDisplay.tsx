import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

import type { ThreatState } from './threatIcons'
import type { Threat } from './types'

/** Head-marker/glyph state derived from track status. `heading`/`directional`
 * only matter on the map (a directional type with no heading yet reads as a
 * plain fix, not a moving arrow) — the feed never passes them and always
 * collapses to 'active'. */
export function threatState(
  threat: Threat,
  opts: { heading?: number | null; directional?: boolean } = {},
): ThreatState {
  if (threat.status === 'impact') return 'impact'
  if (threat.status === 'destroyed' || threat.status === 'lost') return 'destroyed'
  if (opts.directional && opts.heading == null) return 'fix'
  return 'active'
}

/** Localized target-type label, suppressed for an impact with no confirmed
 * type — an "unknown" hit is aftermath (a strike whose weapon nobody
 * named), not worth labelling "unknown" next to the marker. */
export function typeLabel(threat: Threat, t: (key: string) => string): string | null {
  if (threat.status === 'impact' && threat.target_type === 'unknown') return null
  return t(`target.${threat.target_type}`)
}

/** "N sources · X% confidence" — identical wording in the feed and the map
 * popup; `as` picks the wrapper since the popup has no Tailwind (inline
 * styles only) while the feed uses classNames. */
export function CorroborationLine({
  threat,
  as: Tag = 'span',
  className,
  style,
}: {
  threat: Threat
  as?: 'span' | 'div'
  className?: string
  style?: CSSProperties
}) {
  const { t } = useTranslation()
  return (
    <Tag className={className} style={style}>
      {threat.corroboration_count} {t('log.corroboration')} ·{' '}
      {Math.round(threat.confidence * 100)}% {t('log.confidence')}
    </Tag>
  )
}

/** "×N" stated-group-size badge (rendered only when N>1) — amber-400, the
 * app's existing emphasis accent (see App.tsx's header warning button,
 * DisclaimerModal's icon). */
export function CountBadge({
  count,
  as: Tag = 'span',
  className,
  style,
}: {
  count: number
  as?: 'span' | 'b'
  className?: string
  style?: CSSProperties
}) {
  if (count <= 1) return null
  return (
    <Tag className={className} style={style}>
      ×{count}
    </Tag>
  )
}
