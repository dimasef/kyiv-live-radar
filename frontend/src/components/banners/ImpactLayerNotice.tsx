import { Flame } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import { PILL_CLASS, PILL_TONE } from './pillStyles'
import Presence from './Presence'

/** What just happened to the impact layer — the twin of ZoneLayerNotice, for
 * the same reason: the switch sits in a corner while its effect is the whole
 * map. Only the accounts that have the switch can ever raise it. */
export default function ImpactLayerNotice() {
  const { t } = useTranslation()
  const notice = useRadar((s) => s.impactLayerNotice)

  return (
    <Presence visible={notice !== null}>
      <div role="status" className={`${PILL_CLASS} ${PILL_TONE.layer}`}>
        <Flame size={14} className="flex-none" />
        {notice === 'off' ? t('impacts.noticeOff') : t('impacts.noticeOn')}
      </div>
    </Presence>
  )
}
