import { useTranslation } from 'react-i18next'

import { currentRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import { isInFeed, isPinnedRegion } from '@/store/feedRegions'
import type { RegionInfo } from '@/types'

/** What a click on an oblast opens: what the region is to this reader, and the
 * one thing they can do about it. The FOLLOWED region gets the state line only
 * — it is what this reader is here for and has no "off" (which is not the same
 * as `region.is_home`; see store/feedRegions.isPinnedRegion). */
export default function RegionMenu({ region }: { region: RegionInfo }) {
  const { t } = useTranslation()
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const toggleFeedRegion = useRadar((s) => s.toggleFeedRegion)
  const followed = useRadar((s) => currentRegion(s))
  const pinned = isPinnedRegion(region.id, followed)
  const inFeed = isInFeed(region.id, feedExtraRegions, followed)

  return (
    <div className="min-w-[9rem]">
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
        <button
          onClick={() => toggleFeedRegion(region.id)}
          className={`mt-2 w-full rounded-lg px-2.5 py-1.5 text-[13px] font-semibold transition-colors duration-200 ${
            inFeed
              ? 'border border-white/15 text-slate-300 hover:bg-white/[0.06]'
              : 'bg-phosphor text-ink-950 hover:opacity-90'
          }`}
        >
          {t(inFeed ? 'regionMenu.remove' : 'regionMenu.add')}
        </button>
      )}
    </div>
  )
}
