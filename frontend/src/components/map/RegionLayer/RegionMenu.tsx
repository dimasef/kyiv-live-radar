import { useTranslation } from 'react-i18next'

import { currentRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import { isInFeed, isPinnedRegion } from '@/store/feedRegions'
import type { RegionInfo } from '@/types'

/** What a click on an oblast opens: what the region is to this reader, and the
 * two things they can do about it — put its sources' events in the feed, or make
 * it the region they follow.
 *
 * The FOLLOWED region gets neither button: it is always in the feed and has no
 * "off" (which is not the same as `region.is_home`; see
 * store/feedRegions.isPinnedRegion), and it is already primary. */
export default function RegionMenu({ region }: { region: RegionInfo }) {
  const { t } = useTranslation()
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const toggleFeedRegion = useRadar((s) => s.toggleFeedRegion)
  const setChosenRegion = useRadar((s) => s.setChosenRegion)
  const followed = useRadar((s) => currentRegion(s))
  const pinned = isPinnedRegion(region.id, followed)
  const inFeed = isInFeed(region.id, feedExtraRegions, followed)

  return (
    <div className="min-w-[10rem]">
      <p className="font-display text-sm font-bold text-slate-100">{region.name_uk}</p>
      <p className="mt-0.5 text-[11px] text-slate-400">
        {pinned
          ? t('regionMenu.home')
          : inFeed
            ? t('regionMenu.inFeed')
            : t('regionMenu.outOfFeed')}
      </p>
      {!region.active && (
        <p className="mt-0.5 text-[11px] text-slate-500">{t('regionMenu.pending')}</p>
      )}
      {!pinned && (
        <div className="mt-2 flex flex-col gap-1.5">
          <button
            onClick={() => toggleFeedRegion(region.id)}
            className={`w-full rounded-lg px-2.5 py-1.5 text-[13px] font-semibold transition-colors duration-200 ${
              inFeed
                ? 'border border-white/15 text-slate-300 hover:bg-white/[0.06]'
                : 'bg-phosphor text-ink-950 hover:opacity-90'
            }`}
          >
            {t(inFeed ? 'regionMenu.remove' : 'regionMenu.add')}
          </button>
          <button
            onClick={() => setChosenRegion(region.id)}
            className="w-full rounded-lg border border-white/15 px-2.5 py-1.5 text-[13px] font-semibold text-slate-300 transition-colors duration-200 hover:bg-white/[0.06]"
          >
            {t('regionMenu.makePrimary')}
          </button>
          {/* Switching is not additive: the region being left keeps its events
              only if it was ALSO added as an extra, and the alerts that may
              notify move with the choice. Worth one line — the same action in
              settings sits under a heading that says so, and here it doesn't. */}
          <p className="text-[10px] leading-tight text-slate-500">
            {t('regionMenu.makePrimaryHint')}
          </p>
        </div>
      )}
    </div>
  )
}
