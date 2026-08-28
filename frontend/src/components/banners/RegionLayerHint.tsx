import { Map as MapIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import { PILL_CLASS, PILL_TONE } from './pillStyles'
import Presence from './Presence'

/** Says, once ever, that the oblasts on screen can be clicked.
 *
 * The map opens fitted to the city, so nothing brings a reader to the zoom the
 * region layer lives at, and an outline that reacts to nothing is not a hint.
 * Raised the first time the threshold is crossed and never again (the "once"
 * lives in store/regionsSlice, keyed in localStorage).
 *
 * Follows ZoneLayerNotice's two rules: it stacks under the alert/attack banner
 * rather than replacing it, and it is role="status" — a map affordance
 * announced the way a raid is announced would be worse than silence.
 */
export default function RegionLayerHint() {
  const { t } = useTranslation()
  const visible = useRadar((s) => s.regionHintVisible)

  return (
    <Presence visible={visible}>
      <div role="status" className={`${PILL_CLASS} ${PILL_TONE.layer}`}>
        <MapIcon size={14} className="flex-none" />
        {t('regionMenu.hint')}
      </div>
    </Presence>
  )
}
