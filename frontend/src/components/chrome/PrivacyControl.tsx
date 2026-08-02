import { EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import Switch from './Switch'

/** What other people can see about you. Currently one switch — the last-seen
 * timestamp — but this is the block anything of that kind belongs in, which is
 * why it exists as its own section rather than as a loose row somewhere.
 *
 * Sharing your HOME is deliberately not here: it's a property of the home you
 * just placed (and meaningless without one), so it sits in that block instead.
 *
 * Hidden when signed out — with no account there are no contacts to be visible
 * to, and the preference is stored server-side. */
export default function PrivacyControl() {
  const { t } = useTranslation()
  const authed = useRadar((s) => s.authStatus === 'authed')
  const sharePresence = useRadar((s) => s.sharePresence)
  const setSharePresence = useRadar((s) => s.setSharePresence)

  if (!authed) return null

  return (
    <div className="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center gap-2">
        <EyeOff size={13} className="text-phosphor-soft/80" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {t('settings.privacy')}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 text-[13px] text-slate-200">{t('presence.shareLabel')}</p>
        <Switch
          checked={sharePresence}
          label={t('presence.shareLabel')}
          onChange={() => void setSharePresence(!sharePresence).catch(() => {})}
        />
      </div>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">{t('presence.shareHint')}</p>
    </div>
  )
}
