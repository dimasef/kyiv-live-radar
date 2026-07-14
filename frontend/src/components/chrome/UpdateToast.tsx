import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRegisterSW } from 'virtual:pwa-register/react'

/** Bottom-center banner shown when a new build is waiting. `useRegisterSW` also
 * REGISTERS the service worker on mount (the app's single registration point).
 * registerType is 'prompt' (see vite.config.ts) so a safety-adjacent app never
 * strands an open tab on a stale bundle — the user explicitly reloads. */
export default function UpdateToast() {
  const { t } = useTranslation()
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  if (!needRefresh) return null

  return (
    <div
      role="status"
      className="panel fixed bottom-4 left-1/2 z-[2000] flex -translate-x-1/2 items-center gap-3 px-4 py-2.5 shadow-xl"
    >
      <span className="text-xs text-slate-200">{t('update.available')}</span>
      <button className="btn btn--accent text-xs" onClick={() => updateServiceWorker(true)}>
        {t('update.reload')}
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
