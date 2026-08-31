import { Bug } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import SettingsRow from './SettingsRow'

/** "Report a bug" row in Settings, under the version. Deliberately next to the
 * version number: that is what a person looks at when something is wrong. */
export default function ReportBugControl() {
  const { t } = useTranslation()
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  const setBugReportOpen = useRadar((s) => s.setBugReportOpen)

  return (
    <SettingsRow
      icon={<Bug size={13} className="flex-none text-slate-500" />}
      label={t('bug.title')}
      onClick={() => {
        setSettingsOpen(false)
        setBugReportOpen(true)
      }}
    />
  )
}
