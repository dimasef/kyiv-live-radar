import { Bug, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** "Report a bug" row in Settings, under the version. Deliberately next to the
 * version number: that is what a person looks at when something is wrong. */
export default function ReportBugControl() {
  const { t } = useTranslation()
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  const setBugReportOpen = useRadar((s) => s.setBugReportOpen)

  return (
    <button
      onClick={() => {
        setSettingsOpen(false)
        setBugReportOpen(true)
      }}
      className="group mt-3 flex w-full items-center justify-between gap-2 border-t border-white/[0.06] pt-3 text-left"
    >
      <span className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
        <Bug size={13} />
        {t('bug.title')}
      </span>
      <ChevronRight size={13} className="text-slate-500 group-hover:text-slate-300" />
    </button>
  )
}
