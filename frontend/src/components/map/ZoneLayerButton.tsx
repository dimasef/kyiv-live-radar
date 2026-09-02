import { Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import { useShownRegions } from '@/store/useShownRegions'

import { useZoneStates } from './useZoneStates'

import { alertedZones, inShownRegions } from './alertZones'
import { ZONE_STYLES } from './constants'
import { mapControlClass } from './controlStyles'

/** Switches the raion air-alert layer on and off. Carries a count badge while
 * sirens are up, so the layer is discoverable exactly when it matters — that is
 * also the moment the operator would otherwise not know it exists.
 *
 * What the press DID is announced by banners/ZoneLayerNotice, up in the
 * top-centre stack: the effect of this button is the whole screen, and a
 * control in the corner can't show it. */
export default function ZoneLayerButton() {
  const { t } = useTranslation()
  const on = useRadar((s) => s.zoneLayerOn)
  const toggle = useRadar((s) => s.toggleZoneLayer)
  // Counted over the reader's own regions only, or the badge would advertise
  // sirens the layer does not draw — and pressing it would then show nothing.
  const shown = useShownRegions()
  const count = alertedZones(inShownRegions(useZoneStates(), shown)).length

  return (
    <button
      onClick={toggle}
      // The count belongs in the label, not just in the badge: "3" beside a
      // siren says nothing about 3 of WHAT in an app whose subject is targets.
      aria-label={`${t(on ? 'zonesCtl.hide' : 'zonesCtl.show')}${
        count > 0 ? `, ${t('zones.ariaCount', { count })}` : ''
      }`}
      aria-pressed={on}
      title={t('zones.title')}
      className={`${mapControlClass(on)} relative`}
    >
      <Siren size={17} />
      {count > 0 && (
        <span
          className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
          // The zone red, not rose-500: the badge counts the very raions this
          // layer paints, and two reds a shade apart read as a mistake.
          style={{ background: ZONE_STYLES.alert.color }}
        >
          {count}
        </span>
      )}
    </button>
  )
}
