import { Loader2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useRegisterSW } from 'virtual:pwa-register/react'

// How often a long-open tab re-checks prod for a new build. A threat radar is
// typically left open for hours during an alert, so without this poll it would
// only notice a deploy on a manual reload.
const UPDATE_POLL_MS = 15 * 60 * 1000

/** Bottom-center banner shown when a new build is waiting. `useRegisterSW` also
 * REGISTERS the service worker on mount (the app's single registration point).
 * registerType is 'prompt' (see vite.config.ts) so a safety-adjacent app never
 * strands an open tab on a stale bundle — the user explicitly reloads. */
export default function UpdateToast() {
  const { t } = useTranslation()
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    // Surface a fresh deploy on an already-open tab without a manual reload:
    // poll every 15 min and re-check the moment the tab is brought back to the
    // foreground. update() finding a new SW flips needRefresh -> the toast shows.
    onRegisteredSW(_swUrl, reg) {
      if (!reg) return
      const check = () => {
        if (navigator.onLine) reg.update().catch(() => {})
      }
      setInterval(check, UPDATE_POLL_MS)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') check()
      })
    },
  })
  const [nextVersion, setNextVersion] = useState<string | null>(null)
  // Clicking reload takes a few seconds (SW activation + full page reload) —
  // without feedback it reads as a dead button.
  const [updating, setUpdating] = useState(false)

  // Ask the waiting SW (the freshly-installed new build) which version it is.
  useEffect(() => {
    if (!needRefresh) {
      setNextVersion(null)
      return
    }
    let cancelled = false
    navigator.serviceWorker?.getRegistration().then((reg) => {
      const sw = reg?.waiting ?? reg?.installing
      if (!sw) return
      const channel = new MessageChannel()
      channel.port1.onmessage = (e) => {
        if (!cancelled && typeof e.data === 'string') setNextVersion(e.data)
      }
      sw.postMessage({ type: 'GET_VERSION' }, [channel.port2])
    })
    return () => {
      cancelled = true
    }
  }, [needRefresh])

  if (!needRefresh) return null

  return (
    <div
      role="status"
      className="panel fixed bottom-4 left-1/2 z-[2000] flex w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 px-4 py-2.5 shadow-xl"
    >
      <span className="whitespace-nowrap text-xs text-slate-200">{t('update.available')}</span>
      {nextVersion && (
        <span className="whitespace-nowrap rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-phosphor-soft">
          v{nextVersion}
        </span>
      )}
      <button
        className="btn btn--accent flex items-center gap-1.5 text-xs"
        disabled={updating}
        onClick={() => {
          setUpdating(true)
          void updateServiceWorker(true)
        }}
      >
        {updating && <Loader2 size={13} className="animate-spin" />}
        {updating ? t('update.reloading') : t('update.reload')}
      </button>
      <button
        className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-slate-400 transition-colors duration-200 hover:bg-white/10 hover:text-slate-100"
        onClick={() => setNeedRefresh(false)}
        aria-label={t('update.dismiss')}
        title={t('update.dismiss')}
      >
        <X size={13} />
      </button>
    </div>
  )
}
