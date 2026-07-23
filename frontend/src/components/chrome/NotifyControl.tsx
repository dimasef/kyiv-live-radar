import { Bell, BellOff, BellRing } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchPushConfig } from '../../api'
import { useRadar } from '../../store'
import NotifyPrefsControl from './NotifyPrefsControl'

const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true
const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent)

/** Fetched once per session — whether the backend has VAPID keys configured.
 * Module-level (not store): purely this control's visibility concern. The
 * PROMISE is cached so re-renders while it's in flight don't re-fetch. */
let serverEnabled: Promise<boolean> | null = null
function checkServerEnabled(): Promise<boolean> {
  serverEnabled ??= fetchPushConfig()
    .then((c) => c.enabled)
    .catch(() => false)
  return serverEnabled
}

/** "Danger near home" push opt-in — rendered inside the settings drawer. Hidden when
 * the browser can't push or the server has no VAPID keys; on iOS push only
 * works from an installed PWA (16.4+), so an uninstalled iOS Safari gets the
 * install hint instead of a dead toggle. */
export default function NotifyControl() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const notifyStatus = useRadar((s) => s.notifyStatus)
  const enableNotify = useRadar((s) => s.enableNotify)
  const disableNotify = useRadar((s) => s.disableNotify)
  const [visible, setVisible] = useState<boolean | null>(null)

  if (notifyStatus === 'unsupported' && !isIOS()) return null
  if (visible === null) {
    void checkServerEnabled().then(setVisible)
    return null
  }
  if (!visible) return null

  const iosNeedsInstall = isIOS() && !isStandalone() && notifyStatus === 'unsupported'
  const on = notifyStatus === 'on'

  return (
    <div className="mt-2.5 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
          <BellRing size={13} className="flex-none text-phosphor-soft/80" />
          {t('notify.title')}
        </span>
      </div>

      {iosNeedsInstall ? (
        <p className="text-xs leading-snug text-slate-500">{t('notify.iosInstallFirst')}</p>
      ) : notifyStatus === 'denied' ? (
        <p className="text-xs leading-snug text-slate-500">{t('notify.denied')}</p>
      ) : !home ? (
        <p className="text-xs leading-snug text-slate-500">{t('notify.needHome')}</p>
      ) : (
        <>
          <button
            onClick={() => void (on ? disableNotify() : enableNotify())}
            disabled={notifyStatus === 'pending'}
            className={`btn flex w-full items-center justify-center gap-1.5 ${
              on ? 'btn--warn' : 'btn--accent'
            }`}
          >
            {on ? <BellOff size={13} /> : <Bell size={13} />}
            {notifyStatus === 'pending'
              ? t('notify.pending')
              : on
                ? t('notify.disable')
                : t('notify.enable')}
          </button>
          {on && <NotifyPrefsControl />}
        </>
      )}

      <p className="mt-2.5 text-xs leading-snug text-slate-500">{t('notify.policy')}</p>
    </div>
  )
}
