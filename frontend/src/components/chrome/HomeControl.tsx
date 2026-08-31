import { Home, LocateFixed, MapPin, X } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { districtAt } from '@/lib/geo'
import { insideWatchedRegions } from '@/lib/regions'
import { MAP_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

import HomeMarkerRow from './HomeMarkerRow'
import SettingsSection from './SettingsSection'
import ShareHomeToggle from './ShareHomeToggle'

/** Why a location request produced no home. 'implausible' is the interesting
 * one: the browser answered, confidently, with a point outside every watched
 * region — the signature of a jammed GNSS fix during a raid. */
export type GeoFailure = 'denied' | 'implausible'

/** Request the browser geolocation and set it as home (origin 'geo'), unless
 * the fix lands somewhere the reader could not plausibly live.
 *
 * Only ever called from the button. Nothing in the app asks for a location on
 * its own — see the note in store/bootstrap.ts. */
export function requestGeolocation(onFail?: (reason: GeoFailure) => void) {
  if (!('geolocation' in navigator)) {
    onFail?.('denied')
    return
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude: lat, longitude: lon } = pos.coords
      const state = useRadar.getState()
      if (!insideWatchedRegions(state.regions, lat, lon)) {
        onFail?.('implausible')
        return
      }
      state.setHome({ lat, lon, radiusKm: state.home?.radiusKm ?? 3, origin: 'geo' })
    },
    () => onFail?.('denied'),
    { enableHighAccuracy: true, timeout: 8000 },
  )
}

const RADIUS_MIN = 1
const RADIUS_MAX = 15

/** "My home" section — rendered inside the settings drawer (no own panel chrome). */
export default function HomeControl() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const boundaries = useRadar((s) => s.boundaries)
  const setHome = useRadar((s) => s.setHome)
  const setHomeRadius = useRadar((s) => s.setHomeRadius)
  const placingHome = useRadar((s) => s.placingHome)
  const setPlacingHome = useRadar((s) => s.setPlacingHome)
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  const [geoFailure, setGeoFailure] = useState<GeoFailure | null>(null)

  // Placing home needs the map visible — leave the drawer (and any sub-page).
  const togglePlacing = () => {
    const next = !placingHome
    setPlacingHome(next)
    if (next) {
      setSettingsOpen(false)
      navigate(MAP_PATH)
    }
  }

  const homeDistrict = home ? districtAt(home.lat, home.lon, boundaries) : null
  const fill = home
    ? `${((home.radiusKm - RADIUS_MIN) / (RADIUS_MAX - RADIUS_MIN)) * 100}%`
    : '0%'

  return (
    <SettingsSection
      icon={Home}
      title={t('home.title')}
      action={
        home && (
          <button
            onClick={() => setHome(null)}
            className="text-sm text-red-400 underline decoration-red-400/40 underline-offset-2 transition-colors hover:text-red-300"
          >
            {t('home.clear')}
          </button>
        )
      }
    >
      {home ? (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono text-sm text-phosphor-soft">
              {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
            </span>
            {homeDistrict && (
              <span className="truncate text-sm text-slate-400">
                {homeDistrict}
              </span>
            )}
          </div>
          <label className="mt-2.5 flex items-baseline justify-between text-sm text-slate-400">
            <span>{t('home.radius')}</span>
            <span className="font-mono text-slate-200">{home.radiusKm} {t('home.km')}</span>
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
        <div className="text-sm text-slate-500">{t('home.notSet')}</div>
      )}

      {/* Manual placement is the accented one: it is the way that works during
          a raid, when jamming makes a location fix a confident lie (see
          requestGeolocation). "My location" stays — it is genuinely the fastest
          route on a quiet evening — but it no longer looks like the answer. */}
      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <button
          onClick={togglePlacing}
          className={`btn flex items-center justify-center gap-1.5 ${
            placingHome ? 'btn--warn' : 'btn--accent'
          }`}
        >
          {placingHome ? <X size={13} /> : <MapPin size={13} />}
          {placingHome ? t('home.cancel') : t('home.place')}
        </button>
        <button
          onClick={() => {
            setGeoFailure(null)
            requestGeolocation(setGeoFailure)
          }}
          className="btn flex items-center justify-center gap-1.5"
        >
          <LocateFixed size={13} />
          {t('home.useGeo')}
        </button>
      </div>
      {(placingHome || geoFailure) && (
        <p
          className={`mt-1.5 text-sm leading-snug ${
            geoFailure === 'implausible' ? 'text-amber-200/90' : 'text-slate-500'
          }`}
        >
          {placingHome
            ? t('home.placing')
            : geoFailure === 'implausible'
              ? t('home.geoImplausible')
              : t('home.geoDenied')}
        </p>
      )}
      <HomeMarkerRow />
      <ShareHomeToggle />
    </SettingsSection>
  )
}
