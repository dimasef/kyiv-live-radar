import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

import type { Threat } from './types'

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
