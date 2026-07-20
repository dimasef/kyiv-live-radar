import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** Only in an installed PWA (standalone launch) does the app "open" like a
 * native app worth a splash — a browser-tab reload doesn't. */
function isStandalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    // iOS Safari's non-standard flag
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  )
}

const MIN_MS = 900 // never flash — hold at least this long
const MAX_MS = 2600 // never hang if the backend is slow/down
const FADE_MS = 500

/** A brief branded splash on PWA launch: the radar sweep + app name, fading out
 * once the map data is in (or a fallback timeout). Renders nothing in a browser
 * tab. Synchronizes with external timers/data, so useEffect is the right tool. */
export default function SplashScreen() {
  const { t } = useTranslation()
  const districtsLoaded = useRadar((s) => s.districts.length > 0)
  const [phase, setPhase] = useState<'show' | 'fade' | 'gone'>(() =>
    isStandalone() ? 'show' : 'gone',
  )
  const [start] = useState(() => performance.now())

  // Ready (map data arrived) -> begin fade, but not before MIN_MS so it never flashes.
  useEffect(() => {
    if (phase !== 'show' || !districtsLoaded) return
    const wait = Math.max(0, MIN_MS - (performance.now() - start))
    const id = window.setTimeout(() => setPhase('fade'), wait)
    return () => clearTimeout(id)
  }, [phase, districtsLoaded, start])

  // Fallback: fade out regardless if data never comes.
  useEffect(() => {
    if (phase !== 'show') return
    const id = window.setTimeout(() => setPhase('fade'), MAX_MS)
    return () => clearTimeout(id)
  }, [phase])

  // Unmount after the fade transition completes.
  useEffect(() => {
    if (phase !== 'fade') return
    const id = window.setTimeout(() => setPhase('gone'), FADE_MS)
    return () => clearTimeout(id)
  }, [phase])

  if (phase === 'gone') return null

  return (
    <div
      aria-hidden
      className={`fixed inset-0 z-[3000] flex flex-col items-center justify-center gap-6 bg-[#05080d] transition-opacity duration-500 ${
        phase === 'fade' ? 'pointer-events-none opacity-0' : 'opacity-100'
      }`}
    >
      <img src="/favicon-animated.svg" alt="" aria-hidden className="h-24 w-24" />
      <div className="flex flex-col items-center gap-1">
        <div className="font-display text-base font-bold tracking-wide text-slate-100">
          {t('app.title')}
        </div>
        <div className="font-mono text-[11px] text-slate-500">{t('app.subtitle')}</div>
      </div>
    </div>
  )
}
