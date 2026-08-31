import { Tag } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { APP_VERSION } from '@/changelog'
import { CHANGELOG_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

import SettingsRow from './SettingsRow'

/** App version row in Settings. Links to the standalone /change-log page (a
 * real URL, so it can be shared — hence the anchor SettingsRow renders). */
export default function VersionInfo() {
  const { t } = useTranslation()
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  return (
    <SettingsRow
      icon={<Tag size={13} className="flex-none text-slate-500" />}
      label={t('changelog.version')}
      sub={t('changelog.history')}
      right={<span className="font-mono text-sm text-phosphor-soft">v{APP_VERSION}</span>}
      href={CHANGELOG_PATH}
      onClick={() => {
        setSettingsOpen(false)
        navigate(CHANGELOG_PATH)
      }}
    />
  )
}
