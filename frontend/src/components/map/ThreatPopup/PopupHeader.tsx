import { useTranslation } from 'react-i18next'

import { threatColor } from '@/theme'
import { CountBadge, typeLabel } from '@/threatDisplay'
import { threatChip } from '@/threatLabels'
import type { Threat } from '@/types'

import AdminEditButton from './AdminEditButton'
import { MONO } from './popupStyles'

/** Target identity in one line: type, stated group size, lifecycle chip.
 *
 * The type carries the marker's own colour instead of a separate swatch beside
 * it — a coloured dot next to a coloured status chip read as two status lights
 * disagreeing, when only one of them ever meant status. */
export default function PopupHeader({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const color = threatColor(threat)
  // Same source as the feed's StatusChip — the two must never disagree.
  const chip = threatChip(threat)
  const label = typeLabel(threat, t)

  return (
    // wrap: type name + ×N + a long chip ("НЕ ПІДТВЕРДЖЕНО") together exceed the
    // popup's width, and wrapping beats overflowing. The right padding is the
    // close button's seat — Leaflet floats it over this corner.
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 6,
        flexWrap: 'wrap',
        paddingRight: 14,
      }}
    >
      {label && <b style={{ fontSize: 14, color }}>{label}</b>}
      <CountBadge count={threat.target_count} as="b" style={{ color: '#fbbf24', fontFamily: MONO }} />
      {/* Lifecycle chip — same idiom as the feed's StatusChip (uppercase
          micro-caps on a 10%-alpha wash of its own colour), so one state looks
          the same wherever it appears. */}
      <span
        style={{
          padding: '1px 4px',
          borderRadius: 4,
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          whiteSpace: 'nowrap',
          color: chip.color,
          background: `${chip.color}1a`,
        }}
      >
        {t(chip.labelKey)}
      </span>
      {/* Admin only, and deliberately last: it rides whatever room the line has
          left rather than claiming a section of its own. */}
      <AdminEditButton threat={threat} />
    </div>
  )
}
