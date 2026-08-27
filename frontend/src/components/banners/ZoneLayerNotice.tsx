import { Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import { PILL_CLASS, PILL_TONE } from './pillStyles'
import Presence from './Presence'

/** What just happened to the raion-alert layer, said once and taken back after
 * a few seconds (the timer lives in store/zonesSlice).
 *
 * It exists because the switch is in the bottom-left corner of the map while
 * its effect is the whole screen: pressing it used to produce no confirmation
 * anywhere near the eye, and on a TV or a phone the operator could not tell an
 * empty layer from a layer that had failed to come on.
 *
 * Two rules this must not break:
 *  - It STACKS UNDER the alert/attack banner, never replaces it. App.tsx
 *    renders that slot as a column, so both fit; the line that says what is in
 *    the sky is not something a layer switch may take.
 *  - role="status", never "alert". A screen reader announcing a map layer the
 *    way it announces a raid would be worse than saying nothing.
 */
export default function ZoneLayerNotice() {
  const { t } = useTranslation()
  const notice = useRadar((s) => s.zoneLayerNotice)

  // No raion tally here. The layer it just drew IS the tally, in the place the
  // eye is already headed; repeating it as a number would make the operator
  // read the same fact twice.
  return (
    <Presence visible={notice !== null}>
      <div role="status" className={`${PILL_CLASS} ${PILL_TONE.layer}`}>
        <Siren size={14} className="flex-none" />
        {/* Two whole t() calls rather than one with a computed key: the
            locales/keys.test.ts scan only sees a literal, and a key it cannot
            see is a key that can go missing from a bundle unnoticed. */}
        {notice === 'off' ? t('zones.noticeOff') : t('zones.noticeOn')}
      </div>
    </Presence>
  )
}
