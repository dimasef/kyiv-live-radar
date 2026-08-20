import { Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import { alertedZones } from './alertZones'
import { mapControlClass } from './controlStyles'

/** Switches the raion air-alert layer on and off. Carries a count badge while
 * sirens are up, so the layer is discoverable exactly when it matters — that is
 * also the moment the operator would otherwise not know it exists. */
export default function ZoneLayerButton() {
  const { t } = useTranslation()
  const on = useRadar((s) => s.zoneLayerOn)
  const toggle = useRadar((s) => s.toggleZoneLayer)
  const count = alertedZones(useRadar((s) => s.zones)).length

  return (
    <button
      onClick={toggle}
      aria-label={t(on ? 'zonesCtl.hide' : 'zonesCtl.show')}
      aria-pressed={on}
      title={t('zones.title')}
      className={`${mapControlClass(on)} relative`}
    >
      <Siren size={17} />
      {count > 0 && (
        <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
          {count}
        </span>
      )}
    </button>
  )
}
