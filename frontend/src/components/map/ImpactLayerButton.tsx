import { Flame } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { canSeeImpacts } from '@/api'
import { useRadar } from '@/store'
import { ZONE_STYLES } from './constants'
import { mapControlClass } from './controlStyles'

/** Switches the consequence layer on and off — confirmed hits and what a
 * strike did to a raion, both halves at once. Shown only to the accounts an
 * operator has vouched for.
 *
 * Hiding the button from everyone else is presentation, not protection: the
 * route behind it 403s on its own (models.IMPACT_ROLES), and it has to, because
 * a hidden button is one devtools away. What hiding buys is that a regular
 * reader is never offered a switch that would only tell them no. */
export default function ImpactLayerButton() {
  const { t } = useTranslation()
  const allowed = useRadar((s) => canSeeImpacts(s.user?.role))
  const on = useRadar((s) => s.impactLayerOn)
  const toggle = useRadar((s) => s.toggleImpactLayer)
  // Both halves of the layer, because the badge answers "is there anything
  // under this button" and a night with reports but no confirmed hit is the
  // common case (measured: 20 aftermath reports against 5 impacts on the same
  // corpus). Shown while the layer is off as well — that is when the answer is
  // news, the same rule as the siren button beside it.
  const count = useRadar((s) => s.impacts.length + s.aftermath.length)

  if (!allowed) return null

  return (
    <button
      onClick={toggle}
      aria-label={t(on ? 'impacts.hide' : 'impacts.show')}
      aria-pressed={on}
      title={t('impacts.title')}
      className={`${mapControlClass(on)} relative`}
    >
      <Flame size={17} />
      {count > 0 && (
        <span
          className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
          // The same red as the siren button's badge: the two corners count
          // different things, but a badge is a badge, and one colour for both
          // is what stops the pair reading as two different alarms.
          style={{ background: ZONE_STYLES.red.color }}
        >
          {count}
        </span>
      )}
    </button>
  )
}
