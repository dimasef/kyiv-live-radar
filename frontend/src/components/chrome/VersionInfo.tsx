import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { APP_VERSION } from '../../changelog'
import { CHANGELOG_PATH, navigate } from '../../router'
import { useRadar } from '../../store'

/** App version row in Settings (under "My home"). Links to the standalone
 * /change-log page (a real URL, so it can be shared). */
export default function VersionInfo() {
  const { t } = useTranslation()
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  return (
    <div className="mt-3 border-t border-white/[0.06] pt-3">
      <a
        href={CHANGELOG_PATH}
        onClick={(e) => {
          e.preventDefault()
          setSettingsOpen(false)
          navigate(CHANGELOG_PATH)
        }}
        className="group flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
          {t('changelog.version')}
          <span className="font-mono normal-case tracking-normal text-phosphor-soft">
            v{APP_VERSION}
          </span>
        </span>
        <span className="flex items-center gap-1 text-[11px] text-slate-500 transition-colors group-hover:text-slate-300">
          {t('changelog.history')}
          <ChevronRight size={13} />
        </span>
      </a>
    </div>
  )
}
