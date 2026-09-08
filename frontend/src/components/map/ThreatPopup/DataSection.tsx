import { useTranslation } from 'react-i18next'

import { isQuiet, minutesSinceSeen } from '@/lib/threatFreshness'
import { useRadar } from '@/store'
import { CorroborationLine } from '@/threatDisplay'
import type { Threat } from '@/types'

import PopupSection from './PopupSection'
import { MONO, row } from './popupStyles'
import { sourceSplit } from './sources'

/** How much this target is worth believing: who reported it, how confident the
 * fusion is, how old that is, and whether the sources contradict each other. */
export default function DataSection({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const now = useRadar((s) => s.nowMs + s.clockSkewMs)
  const { lead, echoCount, echoSources } = sourceSplit(threat)

  return (
    <PopupSection label={t('popup.data')}>
      <CorroborationLine threat={threat} as="div" style={row} />
      {/* Channel names as chips rather than run together in a sentence. They
          are proper names, several of them carry their own punctuation
          («Місто Кия | Безпека»), and comma-joining them into a 270px line left
          the operator parsing where one ends and the next begins. */}
      {lead && (
        <div style={{ ...row, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4 }}>
          <span>{t('popup.leadLabel')}</span>
          <SourceChip name={lead} />
          {echoCount > 0 && (
            <>
              <span>{t('popup.echoLabel', { n: echoCount })}</span>
              {echoSources.map((name) => (
                <SourceChip key={name} name={name} />
              ))}
            </>
          )}
        </div>
      )}
      {/* Names the reason a target looks faded — "seen 14 min ago" is the fade
          in words, and the number is what an operator actually acts on. */}
      {isQuiet(threat, now) && (
        <div style={{ ...row, opacity: 0.6 }}>
          {t('threat.lastSeen', { n: minutesSinceSeen(threat, now) })}
        </div>
      )}
      {threat.has_conflict && (
        <div style={{ ...row, color: '#fb923c', fontWeight: 600, opacity: 1 }}>
          ⚠ {t('log.conflict')}
        </div>
      )}
    </PopupSection>
  )
}

/** One channel name.
 *
 * Every chip is identical, including the leading one. It used to carry a
 * brighter fill and border, and on a dark popup that read as a BIGGER chip
 * rather than a more important one — the geometry was the same to the pixel,
 * so the only thing the emphasis conveyed was a size difference that wasn't
 * there. Which channel leads is already said by the «Веде:» label in front of
 * it, and by its position; the chip doesn't need to say it twice.
 */
function SourceChip({ name }: { name: string }) {
  return (
    <span
      style={{
        padding: '0 5px',
        borderRadius: 999,
        border: '1px solid rgba(255,255,255,0.12)',
        background: 'rgba(255,255,255,0.06)',
        fontFamily: MONO,
        fontSize: 11,
        lineHeight: '16px',
        // Clipping a name longer than the 270px popup rather than letting it
        // push past the edge. This works because the chips sit in a flex row,
        // which blockifies them — on a bare inline span, overflow and max-width
        // do nothing at all.
        whiteSpace: 'nowrap',
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      {name}
    </span>
  )
}
