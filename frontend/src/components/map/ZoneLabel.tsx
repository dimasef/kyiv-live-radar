import { CloudOff, ShieldCheck, Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import type { AlertZone } from '@/types'

import { compactSinceLabel, sinceParts, type ZoneTone } from './alertZones'

const TONE_ICON = { alert: Siren, clear: ShieldCheck, stale: CloudOff } as const

/** What a raion permanently says about itself: its state as a glyph, and how
 * long it has held it.
 *
 * The name is NOT here by default. Thirteen raion names sitting over the map at
 * all times is a lot of text to read past, and the name is the one thing an
 * operator watching their own oblast already knows from the shape — while "how
 * long has this siren been up" is the thing they actually came to check. So the
 * standing label is the state, and the name is what appears on demand.
 *
 * Stale shows no duration: when the provider is unreachable, the timestamp we
 * hold is the age of a reading we no longer trust, and dressing it up as "quiet
 * for 40 min" would turn an outage into an all-clear.
 *
 * Split out of AlertZoneLayer so the ticking clock re-renders one line of text
 * rather than every polygon on the layer.
 */
export default function ZoneLabel({
  name,
  zone,
  tone,
  named,
}: {
  name: string
  zone: AlertZone | undefined
  tone: ZoneTone
  /** Hovered or focused — reveal the raion's name under the chip. */
  named: boolean
}) {
  const { t } = useTranslation()
  const nowMs = useRadar((s) => s.nowMs)
  const skew = useRadar((s) => s.clockSkewMs)

  const Icon = TONE_ICON[tone]
  const held =
    tone === 'stale' ? null : compactSinceLabel(sinceParts(zone?.changed_at, nowMs + skew))

  return (
    <>
      <span className={`zone-chip zone-chip--${tone}`}>
        <Icon size={11} strokeWidth={2.4} aria-hidden />
        {held && <span className="zone-chip-time">{t(held.key, held.vars)}</span>}
        {/* The glyph alone is not a label — say the state in words for a screen
            reader, and for anyone who has not learned the three icons yet. */}
        <span className="sr-only">{t(`zones.${tone === 'stale' ? 'noData' : tone}`)}</span>
      </span>
      {named && <span className="zone-label-name">{name}</span>}
    </>
  )
}
