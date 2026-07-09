import { LocateFixed, MapPin, X } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { districtAt } from '../geo'
import { useRadar } from '../store'

/** Request the browser geolocation and set it as home (origin 'geo'). */
export function requestGeolocation(onDenied?: () => void) {
  if (!('geolocation' in navigator)) {
    onDenied?.()
    return
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const cur = useRadar.getState().home
      useRadar.getState().setHome({
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        radiusKm: cur?.radiusKm ?? 3,
        origin: 'geo',
      })
    },
    () => onDenied?.(),
    { enableHighAccuracy: true, timeout: 8000 },
  )
}

const RADIUS_MIN = 1
const RADIUS_MAX = 15

/** "My home" section — rendered inside SettingsPanel (no own panel chrome). */
export default function HomeControl() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const boundaries = useRadar((s) => s.boundaries)
  const setHome = useRadar((s) => s.setHome)
  const setHomeRadius = useRadar((s) => s.setHomeRadius)
  const placingHome = useRadar((s) => s.placingHome)
  const setPlacingHome = useRadar((s) => s.setPlacingHome)
  const [denied, setDenied] = useState(false)

  const homeDistrict = home ? districtAt(home.lat, home.lon, boundaries) : null
  const fill = home
    ? `${((home.radiusKm - RADIUS_MIN) / (RADIUS_MAX - RADIUS_MIN)) * 100}%`
    : '0%'

  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {t('home.title')}
        </span>
        {home && (
          <button
            onClick={() => setHome(null)}
            className="text-[11px] text-slate-500 underline decoration-slate-600 underline-offset-2 transition-colors hover:text-slate-200"
          >
            {t('home.clear')}
          </button>
        )}
      </div>

      {home ? (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono text-xs text-phosphor-soft">
              {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
            </span>
            {homeDistrict && (
              <span className="truncate text-[11px] text-slate-400">
                {homeDistrict}
              </span>
            )}
          </div>
          <label className="mt-2.5 flex items-baseline justify-between text-[11px] text-slate-400">
            <span>{t('home.radius')}</span>
            <span className="font-mono text-slate-200">{home.radiusKm} km</span>
          </label>
          <input
            type="range"
            min={RADIUS_MIN}
            max={RADIUS_MAX}
            step={1}
            value={home.radiusKm}
            onChange={(e) => setHomeRadius(Number(e.target.value))}
            className="range-glow mt-1.5"
            style={{ '--fill': fill } as CSSProperties}
          />
        </>
      ) : (
        <div className="text-xs text-slate-500">{t('home.notSet')}</div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <button
          onClick={() => setPlacingHome(!placingHome)}
          className={`btn flex items-center justify-center gap-1.5 ${
            placingHome ? 'btn--warn' : ''
          }`}
        >
          {placingHome ? <X size={13} /> : <MapPin size={13} />}
          {placingHome ? t('home.cancel') : t('home.place')}
        </button>
        <button
          onClick={() => {
            setDenied(false)
            requestGeolocation(() => setDenied(true))
          }}
          className="btn btn--accent flex items-center justify-center gap-1.5"
        >
          <LocateFixed size={13} />
          {t('home.useGeo')}
        </button>
      </div>
      {(placingHome || denied) && (
        <p className="mt-1.5 text-[11px] leading-snug text-slate-500">
          {placingHome ? t('home.placing') : t('home.geoDenied')}
        </p>
      )}
    </div>
  )
}
