import { Rows3 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { fetchRecentEvents } from '@/api'
import { currentRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import { shownRegions } from '@/store/feedRegions'
import { FEED_LIMITS, type FeedLimit, type FeedTextSize, type SheetHeight } from '@/store/prefsSlice'

import FeedRegionChips from './FeedRegionChips'

const HEIGHTS: SheetHeight[] = ['low', 'mid', 'high']
const SIZES: FeedTextSize[] = ['sm', 'md', 'lg']

const seg = (active: boolean) =>
  `flex-1 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
    active
      ? 'border-phosphor/30 bg-phosphor/15 text-phosphor-soft'
      : 'border-transparent bg-white/[0.04] text-slate-400'
  }`

/** Merged "Event feed" settings module: how tall the mobile sheet opens, the
 * feed text scale, and how many messages we fetch/keep. */
export default function FeedSettings() {
  const { t } = useTranslation()
  const sheetHeight = useRadar((s) => s.sheetHeight)
  const setSheetHeight = useRadar((s) => s.setSheetHeight)
  const feedTextSize = useRadar((s) => s.feedTextSize)
  const setFeedTextSize = useRadar((s) => s.setFeedTextSize)
  const feedLimit = useRadar((s) => s.feedLimit)
  const setFeedLimit = useRadar((s) => s.setFeedLimit)
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const regions = useRadar((s) => s.regions)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const feedShowSource = useRadar((s) => s.feedShowSource)
  const setFeedShowSource = useRadar((s) => s.setFeedShowSource)
  const setLog = useRadar((s) => s.setLog)

  // Changing the count re-fetches the feed so it takes effect immediately.
  // (Toggling a region re-fetches too — that one lives in the store action, so
  // the chips don't have to know.)
  const changeLimit = (n: FeedLimit) => {
    setFeedLimit(n)
    const region = currentRegion({ regions, chosenRegion })
    fetchRecentEvents(n, shownRegions(feedExtraRegions, region))
      .then(setLog)
      .catch(() => {})
  }

  const label = 'mb-1 block text-[11px] text-slate-500'

  return (
    <div className="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center gap-2">
        <Rows3 size={13} className="text-phosphor-soft/80" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {t('settings.feed')}
        </span>
      </div>

      {/* Sheet height — mobile only (desktop feed lives in a fixed sidebar). */}
      <div className="lg:hidden">
        <span className={label}>{t('settings.sheetHeight')}</span>
        <div className="flex gap-1">
          {HEIGHTS.map((o) => (
            <button
              key={o}
              onClick={() => setSheetHeight(o)}
              aria-pressed={sheetHeight === o}
              className={seg(sheetHeight === o)}
            >
              {t(`settings.sheet.${o}`)}
            </button>
          ))}
        </div>
      </div>

      <span className={`${label} mt-3`}>{t('settings.feedText')}</span>
      <div className="flex gap-1">
        {SIZES.map((o) => (
          <button
            key={o}
            onClick={() => setFeedTextSize(o)}
            aria-pressed={feedTextSize === o}
            className={`${seg(feedTextSize === o)} ${
              o === 'sm' ? 'text-xs' : o === 'md' ? 'text-[13px]' : 'text-[15px]'
            }`}
          >
            {t(`settings.feedTextSize.${o}`)}
          </button>
        ))}
      </div>

      <span className={`${label} mt-3`}>{t('settings.feedRegions')}</span>
      <FeedRegionChips />

      {/* Display only — unlike the region filter above, nothing is re-fetched:
          every card already carries its source name. */}
      <span className={`${label} mt-3`}>{t('settings.feedSource')}</span>
      <div className="flex gap-1">
        {[true, false].map((on) => (
          <button
            key={String(on)}
            onClick={() => setFeedShowSource(on)}
            aria-pressed={feedShowSource === on}
            className={seg(feedShowSource === on)}
          >
            {t(on ? 'settings.feedSourceShow' : 'settings.feedSourceHide')}
          </button>
        ))}
      </div>

      <span className={`${label} mt-3`}>{t('settings.feedCount')}</span>
      <div className="flex gap-1">
        {FEED_LIMITS.map((n) => (
          <button
            key={n}
            onClick={() => changeLimit(n)}
            aria-pressed={feedLimit === n}
            className={`${seg(feedLimit === n)} font-mono tabular-nums`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  )
}
