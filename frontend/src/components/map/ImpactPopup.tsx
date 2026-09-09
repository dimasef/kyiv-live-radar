import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { Popup } from 'react-leaflet'

import HomeDistance from '@/components/common/HomeDistance'
import { kyivClock } from '@/lib/kyivTime'
import { minutesSinceSeen } from '@/lib/threatFreshness'
import { useRadar } from '@/store'
import { STATUS_COLORS, TYPE_COLORS } from '@/theme'
import { CountBadge, typeLabel } from '@/threatDisplay'
import type { Threat } from '@/types'

import { dedupeMessages } from './ThreatPopup/messages'
import PopupFooter from './ThreatPopup/PopupFooter'
import { HAIRLINE, MONO } from './ThreatPopup/popupStyles'

const chip = (color: string): CSSProperties => ({
  fontFamily: MONO,
  fontSize: 11,
  padding: '1px 5px',
  borderRadius: 3,
  border: `1px solid ${color}66`,
  color,
})

/** Where a strike landed, when, what it was, and who said so — the same shape
 * as AftermathPopup, because the reader of this layer asks the same question
 * of both markers.
 *
 * Not ThreatPopup: that one is about a target in the air — its speed, its
 * heading, how far it is from home and closing. An impact is a place, and
 * every one of those lines under a «Рух» caption said something untrue about
 * it. What survives from the target popup is the type (a drone hit and a
 * ballistic hit are different news) as a chip beside the place, the distance
 * from home as a plain line, and the messages verbatim. */
export default function ImpactPopup({ threat }: { threat: Threat }) {
  const { t, i18n } = useTranslation()
  const now = useRadar((s) => s.nowMs + s.clockSkewMs)
  const districts = useRadar((s) => s.districts)
  const uk = !i18n.language || i18n.language.startsWith('uk')

  const messages = dedupeMessages(threat.events).reverse()
  const last = threat.events[threat.events.length - 1]
  const district = districts.find((d) => d.id === last?.district_id)
  const place = district ? (uk ? district.name_uk : district.name_en) : null
  const at = last?.event_time ?? threat.created_at
  const mins = minutesSinceSeen(threat, now)
  const type = typeLabel(threat, t)

  return (
    <Popup>
      <div style={{ fontSize: 13 } as CSSProperties}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, paddingRight: 14 }}>
          <strong style={{ color: STATUS_COLORS.impact }}>{place ?? t('impacts.title')}</strong>
          <span style={{ fontFamily: MONO, fontSize: 11, opacity: 0.6 }}>{kyivClock(at)}</span>
          <CountBadge count={threat.target_count} as="b" style={{ color: '#fbbf24', fontFamily: MONO }} />
        </div>

        <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <span style={chip(STATUS_COLORS.impact)}>{t('impacts.chip')}</span>
          {type && <span style={chip(TYPE_COLORS[threat.target_type])}>{type}</span>}
        </div>

        <HomeDistance threat={threat} className="mt-1.5 text-[12px]" />

        {/* The layer reaches back a whole day; "an hour ago" against
            "yesterday" is most of what the marker means. */}
        <div style={{ fontFamily: MONO, fontSize: 12, opacity: 0.7, marginTop: 5 }}>
          {mins < 60
            ? t('aftermath.agoMinutes', { count: mins })
            : t('aftermath.agoHours', { count: Math.floor(mins / 60) })}
        </div>

        {messages.length > 0 && (
          <div
            style={{
              marginTop: 6,
              paddingTop: 6,
              borderTop: `1px solid ${HAIRLINE}`,
              maxHeight: 150,
              overflowY: 'auto',
            }}
          >
            {messages.map((ev) => (
              <div key={ev.id} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', gap: 6, fontSize: 11, opacity: 0.55, fontFamily: MONO }}>
                  <span>{kyivClock(ev.event_time)}</span>
                  {ev.source_name && <span>{ev.source_name}</span>}
                </div>
                <div style={{ fontSize: 12, lineHeight: 1.35, opacity: 0.9, whiteSpace: 'pre-wrap' }}>
                  {ev.raw_text}
                </div>
              </div>
            ))}
          </div>
        )}

        <PopupFooter threat={threat} />
      </div>
    </Popup>
  )
}
