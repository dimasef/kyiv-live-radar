import { MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchRegionAt } from '@/api'
import { useRadar } from '@/store'
import type { Region } from '@/types'

import RegionChoice from './RegionChoice'

/** First run: which oblast is this reader in.
 *
 * Asked rather than inferred. The app can only guess from a browser location
 * the reader may not have granted, and guessing wrong is worse here than asking
 * once — the answer decides what the feed carries, what the map opens on, and
 * which region may notify at all.
 *
 * Where inside the region they live is a SEPARATE setting (the home marker), on
 * purpose: the two change for different reasons and at different rates. Moving
 * house is not the same event as travelling.
 *
 * No dismiss and no backdrop close: every screen behind this is framed on a
 * region, so there is no useful state to return to without an answer.
 */
export default function RegionPickerModal() {
  const { t } = useTranslation()
  const regions = useRadar((s) => s.regions)
  const setChosenRegion = useRadar((s) => s.setChosenRegion)
  const [picked, setPicked] = useState<Region | null>(null)

  // A pre-selection, never a decision: when a location is available, start on
  // the oblast it falls in so the common case is one tap. Silent on failure —
  // no permission, a home abroad, or no network all just leave nothing
  // selected, and the reader picks from the list.
  //
  // Asks the permission API first and gives up unless it is ALREADY granted, so
  // this never raises a browser prompt of its own. Two reasons: a permission
  // dialog stacked on top of the first-run modal is a bad first second, and the
  // app deliberately does not go looking for the reader's location (see
  // store/bootstrap.ts — jamming makes an unrequested fix a liability). A fix
  // that lands outside every watched region selects nothing, which is what
  // keeps a jammed one from quietly choosing an oblast.
  useEffect(() => {
    if (!navigator.geolocation || !navigator.permissions) return
    let cancelled = false
    void navigator.permissions
      .query({ name: 'geolocation' })
      .then(({ state }) => {
        if (cancelled || state !== 'granted') return
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            if (cancelled) return
            void fetchRegionAt(pos.coords.latitude, pos.coords.longitude)
              .then((res) => {
                if (!cancelled && res.region) setPicked(res.region)
              })
              .catch(() => {})
          },
          () => {},
          { timeout: 5000, maximumAge: 600_000 },
        )
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const chosenIsCovered = regions.find((r) => r.id === picked)?.active ?? true

  return (
    <div
      className="fixed inset-0 z-[1600] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={t('regionPicker.title')}
    >
      <div className="panel w-full max-w-sm p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full border border-phosphor/30 bg-phosphor/10 text-phosphor">
            <MapPin size={20} />
          </span>
          <h2 className="font-display text-sm font-bold tracking-wide text-slate-100">
            {t('regionPicker.title')}
          </h2>
        </div>

        <p className="mt-3 text-[13px] leading-relaxed text-slate-400">
          {t('regionPicker.text')}
        </p>

        <div className="mt-4">
          <RegionChoice value={picked} onChange={setPicked} />
        </div>

        {picked && !chosenIsCovered && (
          <p className="mt-3 text-[12px] leading-relaxed text-amber-200/90">
            {t('regionPicker.pending')}
          </p>
        )}

        <button
          disabled={!picked}
          onClick={() => picked && setChosenRegion(picked)}
          className="btn btn--primary mt-5 w-full font-semibold disabled:opacity-40"
        >
          {t('regionPicker.confirm')}
        </button>
      </div>
    </div>
  )
}
