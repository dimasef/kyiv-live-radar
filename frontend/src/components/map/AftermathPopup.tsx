import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { Popup } from 'react-leaflet'

import { minutesSince } from '@/lib/aftermathFreshness'
import { kyivClock } from '@/lib/kyivTime'
import { useRadar } from '@/store'
import { AFTERMATH_COLOR } from '@/theme'
import type { Aftermath } from '@/types'

import { HAIRLINE, MONO } from './ThreatPopup/popupStyles'

/** What happened here, when, and who said so — in that order.
 *
 * Much smaller than `ThreatPopup` because a report has less to say and nothing
 * to predict: no type, no vector, no confidence, no lifecycle. What it does
 * carry is the original message, and that is the point of showing it — a
 * category alone cannot answer "is this marker right?", and the accounts that
 * can open this layer are the ones an operator trusts to judge that.
 */
export default function AftermathPopup({ report }: { report: Aftermath }) {
  const { t } = useTranslation()
  const now = useRadar((s) => s.nowMs + s.clockSkewMs)
  const mins = minutesSince(report, now)

  return (
    <Popup>
      <div style={{ fontSize: 13 } as CSSProperties}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <strong style={{ color: AFTERMATH_COLOR }}>{report.district_name}</strong>
          <span style={{ fontFamily: MONO, fontSize: 11, opacity: 0.6 }}>
            {kyivClock(report.reported_at)}
          </span>
        </div>

        {/* Every category, not just the marker's — the glyph shows the worst
            thing, this is the full answer. */}
        <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {report.categories.map((c) => (
            <span
              key={c}
              style={{
                fontFamily: MONO,
                fontSize: 11,
                padding: '1px 5px',
                borderRadius: 3,
                border: `1px solid ${AFTERMATH_COLOR}66`,
                color: AFTERMATH_COLOR,
              }}
            >
              {t(`aftermath.category.${c}`, c)}
            </span>
          ))}
        </div>

        {/* The age in words. A report is not a target, so this is the only
            "how current is this" cue there is — and the layer reaches back a
            whole day, where the difference between an hour and yesterday is the
            whole meaning. */}
        <div style={{ fontFamily: MONO, fontSize: 12, opacity: 0.7, marginTop: 5 }}>
          {mins < 60
            ? t('aftermath.agoMinutes', { count: mins })
            : t('aftermath.agoHours', { count: Math.floor(mins / 60) })}
        </div>

        <div
          style={{
            marginTop: 6,
            paddingTop: 6,
            borderTop: `1px solid ${HAIRLINE}`,
            fontSize: 12,
            opacity: 0.85,
            whiteSpace: 'pre-wrap',
          }}
        >
          {report.text}
        </div>

        {report.source_name && (
          <div style={{ fontFamily: MONO, fontSize: 10, opacity: 0.5, marginTop: 4 }}>
            {report.source_name}
          </div>
        )}
      </div>
    </Popup>
  )
}
