import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import Switch from './Switch'

/** "Share my home with contacts" — the privacy gate on the home this block just
 * set, so it lives with the home rather than off in a privacy section. Hidden
 * entirely for a signed-out visitor: it's a server-side preference, and there
 * are no contacts to share with without an account. */
export default function ShareHomeToggle() {
  const { t } = useTranslation()
  const authed = useRadar((s) => s.authStatus === 'authed')
  const home = useRadar((s) => s.home)
  const shareHome = useRadar((s) => s.shareHome)
  const setShareHome = useRadar((s) => s.setShareHome)

  if (!authed) return null

  return (
    <div className="mt-3 flex items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
      <div className="min-w-0">
        <p className="text-sm text-slate-200">{t('friends.shareHomeLabel')}</p>
        <p className="text-sm leading-snug text-slate-500">
          {home ? t('friends.shareHomeHint') : t('friends.needHome')}
        </p>
      </div>
      <Switch
        checked={shareHome}
        disabled={!home}
        label={t('friends.shareHomeLabel')}
        onChange={() => void setShareHome(!shareHome).catch(() => {})}
      />
    </div>
  )
}
