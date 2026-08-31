import { BellRing, MapPin, Navigation, Target, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import { useRadar } from '@/store'

/** First-run invitation to place a home, shown over the bottom of the map once
 * the region is picked and nothing is marked yet.
 *
 * It argues rather than instructs, because placing a home is work and the
 * payoff is invisible until it exists: distance and bearing on every target, a
 * notification gate that can finally say "near you", and a map that opens where
 * the reader lives. Without this the setting sits unread behind the drawer and
 * the app quietly stays in its least useful mode.
 *
 * Dismissible, and the dismissal sticks: an overlay that returns on every load
 * to repeat an offer already declined stops being an offer. Nothing is lost —
 * the same action lives in Settings → «Мій дім» for good.
 */
export default function HomeNudge() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const placingHome = useRadar((s) => s.placingHome)
  const setPlacingHome = useRadar((s) => s.setPlacingHome)
  const [dismissed, setDismissed] = useState(() => safeGet(STORAGE_KEYS.homeHint) === '1')

  // Hidden while placement is armed: the map already carries the address search
  // and the confirm buttons, and this would be arguing for what is happening.
  if (home || dismissed || placingHome || chosenRegion == null) return null

  const dismiss = () => {
    safeSet(STORAGE_KEYS.homeHint, '1')
    setDismissed(true)
  }

  const benefits = [
    { icon: Navigation, text: t('home.nudge.distance') },
    { icon: BellRing, text: t('home.nudge.notify') },
    { icon: Target, text: t('home.nudge.framing') },
  ]

  return (
    <div className="pointer-events-auto absolute bottom-[7.6rem] left-1/2 z-[1000] w-[min(92%,24rem)] -translate-x-1/2 lg:bottom-[4.2rem]">
      <div className="panel popover-up p-3.5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <MapPin size={14} className="flex-none text-phosphor-soft" />
            {t('home.nudge.title')}
          </h2>
          <button
            onClick={dismiss}
            aria-label={t('home.nudge.dismiss')}
            className="-m-1 flex-none p-1 text-slate-500 transition-colors hover:text-slate-200"
          >
            <X size={14} />
          </button>
        </div>

        <ul className="mt-2.5 space-y-1.5">
          {benefits.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-start gap-2 text-sm leading-snug text-slate-400">
              <Icon size={13} className="mt-0.5 flex-none text-phosphor-soft/70" />
              {text}
            </li>
          ))}
        </ul>

        <button
          onClick={() => setPlacingHome(true)}
          className="btn btn--accent mt-3 flex w-full items-center justify-center gap-1.5"
        >
          <MapPin size={13} />
          {t('home.nudge.action')}
        </button>
      </div>
    </div>
  )
}
