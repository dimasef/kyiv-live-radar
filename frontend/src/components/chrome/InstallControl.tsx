import { Download, Share, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '../../lib/storage'
import { useRadar } from '../../store'

const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true
const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent)

/** "Install app" control. Chromium fires `beforeinstallprompt` (captured in
 * main.tsx) → a one-tap install button. iOS Safari fires no such event, so we
 * show a manual "Share → Add to Home Screen" hint instead. Hidden entirely once
 * installed (standalone) or dismissed. */
export default function InstallControl() {
  const { t } = useTranslation()
  const installPrompt = useRadar((s) => s.installPrompt)
  const setInstallPrompt = useRadar((s) => s.setInstallPrompt)
  const [dismissed, setDismissed] = useState(
    () => safeGet(STORAGE_KEYS.installDismiss) === '1',
  )

  if (isStandalone() || dismissed) return null

  const canPrompt = installPrompt !== null
  const iosHint = !canPrompt && isIOS()
  if (!canPrompt && !iosHint) return null // nothing actionable on this browser

  const dismiss = () => {
    safeSet(STORAGE_KEYS.installDismiss, '1')
    setDismissed(true)
  }
  const install = async () => {
    if (!installPrompt) return
    await installPrompt.prompt()
    setInstallPrompt(null) // the prompt is one-shot
  }

  return (
    <div className="mt-2.5 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {t('install.title')}
        </span>
        <button
          onClick={dismiss}
          aria-label={t('install.dismiss')}
          title={t('install.dismiss')}
          className="flex h-5 w-5 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-white/10 hover:text-slate-200"
        >
          <X size={12} />
        </button>
      </div>

      {canPrompt ? (
        <button
          onClick={install}
          className="btn btn--accent flex w-full items-center justify-center gap-1.5"
        >
          <Download size={13} />
          {t('install.action')}
        </button>
      ) : (
        <p className="flex flex-wrap items-center gap-1 text-[11px] leading-snug text-slate-400">
          {t('install.iosHintBefore')}
          <Share size={12} className="inline text-phosphor-soft" />
          {t('install.iosHintAfter')}
        </p>
      )}
    </div>
  )
}
