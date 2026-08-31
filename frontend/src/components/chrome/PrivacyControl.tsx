import { EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import SettingsSection from './SettingsSection'
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
    <SettingsSection icon={EyeOff} title={t('settings.privacy')}>
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 text-sm text-slate-200">{t('presence.shareLabel')}</p>
        <Switch
          checked={sharePresence}
          label={t('presence.shareLabel')}
          onChange={() => void setSharePresence(!sharePresence).catch(() => {})}
        />
      </div>
      <p className="mt-2.5 text-sm leading-snug text-slate-500">{t('presence.shareHint')}</p>
    </SettingsSection>
  )
}
