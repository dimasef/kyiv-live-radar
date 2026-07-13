import { Analytics } from '@vercel/analytics/react'
import { ChevronUp, TriangleAlert, WifiOff } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  fetchActiveAlerts,
  fetchActiveIncidents,
  fetchActiveThreats,
  fetchBoundaries,
  fetchDistricts,
  fetchHealth,
  fetchRecentEvents,
  fetchRecentNotices,
} from './api'
import AlertBanner from './components/banners/AlertBanner'
import IncidentBanner from './components/banners/IncidentBanner'
import DisclaimerModal from './components/chrome/DisclaimerModal'
import { requestGeolocation } from './components/chrome/HomeControl'
import LanguageSwitcher from './components/chrome/LanguageSwitcher'
import SettingsPanel from './components/chrome/SettingsPanel'
import ThreatLog from './components/feed/ThreatLog'
import MapView from './components/map/MapView'
import { safeGet, STORAGE_KEYS } from './lib/storage'
import { useRadar } from './store'
import { connectWS } from './ws'

function delay(i: number): CSSProperties {
  return { '--i': i } as CSSProperties
}

export default function App() {
  const { t } = useTranslation()
  const connected = useRadar((s) => s.connected)
  const feedOk = useRadar((s) => s.feedOk)
  const placingHome = useRadar((s) => s.placingHome)
  const inspectedThreatId = useRadar((s) => s.inspectedThreat?.id)
  const setDistricts = useRadar((s) => s.setDistricts)
  const setBoundaries = useRadar((s) => s.setBoundaries)
  const setThreats = useRadar((s) => s.setThreats)
  const setIncidents = useRadar((s) => s.setIncidents)
  const setAlerts = useRadar((s) => s.setAlerts)
  const setLog = useRadar((s) => s.setLog)
  const setNotices = useRadar((s) => s.setNotices)
  const setFeedOk = useRadar((s) => s.setFeedOk)

  // Safety disclaimer: modal on load unless the user opted out; always
  // reachable again via the header warning button.
  const [showDisclaimer, setShowDisclaimer] = useState(
    () => safeGet(STORAGE_KEYS.disclaimerHide) !== '1',
  )

  // Mobile bottom sheet: expanded + which tab is shown.
  const [sheetOpen, setSheetOpen] = useState(false)
  const [tab, setTab] = useState<'feed' | 'settings'>('feed')

  useEffect(() => {
    fetchDistricts().then(setDistricts).catch(() => {})
    fetchBoundaries().then(setBoundaries).catch(() => {})
    fetchActiveThreats().then(setThreats).catch(() => {})
    fetchActiveIncidents().then(setIncidents).catch(() => {})
    fetchActiveAlerts().then(setAlerts).catch(() => {})
    fetchRecentEvents().then(setLog).catch(() => {})
    fetchRecentNotices().then(setNotices).catch(() => {})
    // Hydrate feed health once; live changes arrive via the WS 'health' frame.
    fetchHealth()
      .then((h) => setFeedOk(h.telegram?.feed_ok ?? null))
      .catch(() => {})
    connectWS()
    // Ask for the user's real location on first run (no saved home yet).
    if (!useRadar.getState().home) requestGeolocation()
  }, [setDistricts, setBoundaries, setThreats, setIncidents, setAlerts, setLog, setNotices, setFeedOk])

  // Placing home needs the map visible — collapse the sheet.
  useEffect(() => {
    if (placingHome) setSheetOpen(false)
  }, [placingHome])

  // Inspecting a track from the feed needs the map visible too.
  useEffect(() => {
    if (inspectedThreatId != null) setSheetOpen(false)
  }, [inspectedThreatId])

  return (
    <div className="h-full flex flex-col">
      <header
        className="rise relative z-[1200] flex items-center justify-between gap-3 px-3 sm:px-4 py-2.5 border-b border-white/5 bg-ink-900/70 backdrop-blur-xl"
        style={delay(0)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="radar radar--rings w-9 h-9 sm:w-10 sm:h-10" aria-hidden />
          <div className="min-w-0">
            <h1 className="font-display font-bold text-[13px] sm:text-[15px] tracking-wide text-slate-100 leading-tight truncate">
              {t('app.title')}
            </h1>
            <p className="hidden sm:block text-[11px] text-slate-400 truncate">
              {t('app.subtitle')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <span
            className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-mono transition-colors duration-300 ${
              connected
                ? 'border-emerald-400/20 bg-emerald-400/5 text-emerald-300'
                : 'border-red-400/25 bg-red-400/5 text-red-300'
            }`}
          >
            <span className={`conn-dot ${connected ? 'conn-dot--on' : 'conn-dot--off'}`} />
            <span className="hidden md:inline">
              {connected ? t('conn.online') : t('conn.offline')}
            </span>
          </span>
          {feedOk === false && (
            <span
              className="flex items-center gap-2 rounded-full border border-red-400/25 bg-red-400/5 px-2.5 py-1 text-[11px] font-mono text-red-300"
              title={t('conn.feedUnavailable')}
            >
              <WifiOff size={12} className="flex-none" />
              <span className="hidden md:inline">{t('conn.feedUnavailable')}</span>
            </span>
          )}
          <button
            onClick={() => setShowDisclaimer(true)}
            aria-label={t('disclaimer.reopen')}
            title={t('disclaimer.reopen')}
            className="flex h-7 w-7 items-center justify-center rounded-full border border-amber-500/25 bg-amber-500/5 text-amber-400 transition-all duration-200 hover:bg-amber-500/15 hover:shadow-[0_0_12px_-2px_rgba(245,158,11,0.5)]"
          >
            <TriangleAlert size={14} />
          </button>
          <LanguageSwitcher />
        </div>
      </header>

      <DisclaimerModal open={showDisclaimer} onClose={() => setShowDisclaimer(false)} />

      <main className="relative flex-1 min-h-0 lg:flex">
        {/* Map fills everything; on mobile the sheet floats above it. */}
        <div className="absolute inset-0 lg:static lg:flex-1 lg:min-w-0">
          <MapView />
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex flex-col items-center gap-2 px-3 pt-3">
            <AlertBanner />
            <IncidentBanner />
          </div>
        </div>

        {/* Desktop sidebar */}
        <aside className="hidden lg:flex w-[344px] shrink-0 flex-col gap-3 p-3 min-h-0 border-l border-white/5 bg-ink-900/55 backdrop-blur-xl">
          <div className="rise" style={delay(1)}>
            <SettingsPanel />
          </div>
          <div className="rise flex-1 min-h-0 flex flex-col" style={delay(2)}>
            <ThreatLog />
          </div>
        </aside>

        {/* Mobile bottom sheet */}
        <section
          className={`sheet lg:hidden absolute inset-x-0 bottom-0 z-[1100] h-[62dvh] flex flex-col rounded-t-2xl border-t border-x border-white/10 bg-ink-900/90 backdrop-blur-2xl shadow-[0_-18px_50px_-20px_rgba(0,0,0,0.8)] ${
            sheetOpen ? 'translate-y-0' : 'translate-y-[calc(100%-3.4rem)]'
          }`}
        >
          <button
            onClick={() => setSheetOpen(!sheetOpen)}
            aria-label={sheetOpen ? t('panel.close') : t('panel.open')}
            className="flex-none flex items-center justify-between gap-3 px-4 h-[3.4rem] w-full text-left"
          >
            <span className="flex items-center gap-2.5 min-w-0">
              <span className="w-8 h-1 rounded-full bg-white/15" aria-hidden />
              <span className="panel-title">{t('log.title')}</span>
            </span>
            <ChevronUp
              size={16}
              className={`text-slate-400 transition-transform duration-300 ${
                sheetOpen ? 'rotate-180' : ''
              }`}
              aria-hidden
            />
          </button>

          <div className="flex-none flex gap-1 px-3 pb-2">
            {(['feed', 'settings'] as const).map((k) => (
              <button
                key={k}
                onClick={() => {
                  setTab(k)
                  setSheetOpen(true)
                }}
                className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
                  tab === k
                    ? 'bg-phosphor/15 text-phosphor-soft border border-phosphor/30'
                    : 'bg-white/[0.04] text-slate-400 border border-transparent'
                }`}
              >
                {t(`panel.${k}`)}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto scroll-slim px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {tab === 'feed' ? <ThreatLog /> : <SettingsPanel defaultOpen />}
          </div>
        </section>
      </main>
      <Analytics />
    </div>
  )
}
