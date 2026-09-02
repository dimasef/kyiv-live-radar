import { useTranslation } from 'react-i18next'

import { kyivClock } from '@/lib/kyivTime'
import type { Threat } from '@/types'

import { dedupeMessages } from './messages'
import PopupSection from './PopupSection'
import { MONO } from './popupStyles'

/** The raw spotter reports behind the track, verbatim — the last word on what a
 * target actually is when the parsed summary above looks off.
 *
 * Newest first, against the chronology: the box scrolls at 150px, so on a
 * well-reported target the freshest word — the one that says where it is NOW —
 * was the one you had to scroll down to find. */
export default function MessageList({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const messages = dedupeMessages(threat.events).reverse()
  if (messages.length === 0) return null

  return (
    <PopupSection label={t('popup.messages')}>
      <div style={{ maxHeight: 150, overflowY: 'auto' }}>
        {messages.map((ev) => (
          <div key={ev.id} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', gap: 6, fontSize: 11, opacity: 0.55, fontFamily: MONO }}>
              <span>{kyivClock(ev.event_time)}</span>
              {ev.source_name && <span>{ev.source_name}</span>}
            </div>
            <div style={{ fontSize: 12, lineHeight: 1.35, opacity: 0.9 }}>{ev.raw_text}</div>
          </div>
        ))}
      </div>
    </PopupSection>
  )
}
