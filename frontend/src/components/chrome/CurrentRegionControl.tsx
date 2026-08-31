import { MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import RegionChoice from './RegionChoice'
import SettingsSection from './SettingsSection'

/** The oblast this device follows — picked on first run, changed here.
 *
 * Deliberately NOT the same setting as the home marker above it. This one says
 * WHICH region's targets reach the feed, the map and the notification gate; the
 * home marker says WHERE inside it the danger distance is measured from. They
 * change for different reasons — travelling versus moving house — and tying
 * them together meant a trip broke the alert radius and the home shared with
 * contacts.
 *
 * Per-device (localStorage + the push subscription), so a phone taken elsewhere
 * leaves the desktop at home following its own region.
 */
export default function CurrentRegionControl() {
  const { t } = useTranslation()
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const setChosenRegion = useRadar((s) => s.setChosenRegion)

  return (
    <SettingsSection icon={MapPin} title={t('currentRegion.title')}>
      <span className="mb-2 block text-sm leading-relaxed text-slate-500">
        {t('currentRegion.hint')}
      </span>
      <RegionChoice value={chosenRegion} onChange={setChosenRegion} />
    </SettingsSection>
  )
}
