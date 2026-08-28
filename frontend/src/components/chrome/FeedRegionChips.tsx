import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** Which regions' sightings the feed lists — one chip per declared region.
 *
 * Driven by the server catalogue, so a region added upstream is offerable with
 * no edit here; the `defaultValue` on each label is what lets it render before
 * anyone has written a translation key for it.
 */
// Wrapping chips rather than the flex-1 segments the rest of the drawer uses:
// the count is open-ended, so equal shares would shrink to unreadable as
// regions are added.
const chip = (on: boolean) =>
  `rounded-lg border px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
    on
      ? 'border-phosphor/30 bg-phosphor/15 text-phosphor-soft'
      : 'border-transparent bg-white/[0.04] text-slate-400'
  }`

export default function FeedRegionChips() {
  const { t } = useTranslation()
  const regions = useRadar((s) => s.regions)
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const toggleFeedRegion = useRadar((s) => s.toggleFeedRegion)

  return (
    <div className="flex flex-wrap gap-1">
      {regions.map((region) => {
        const on = region.is_home || feedExtraRegions.includes(region.id)
        return (
          <button
            key={region.id}
            onClick={() => toggleFeedRegion(region.id)}
            aria-pressed={on}
            // The home region is what the radar is about — it has no "off".
            disabled={region.is_home}
            title={region.active ? undefined : t('settings.feedRegionPending')}
            className={`${chip(on)} ${region.is_home ? 'cursor-default' : ''} ${
              region.active ? '' : 'opacity-60'
            }`}
          >
            {t(`feedRegion.${region.id}`, { defaultValue: region.name_uk })}
          </button>
        )
      })}
    </div>
  )
}
