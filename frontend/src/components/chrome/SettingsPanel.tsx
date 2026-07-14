import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '../../lib/storage'
import HomeControl from './HomeControl'
import InstallControl from './InstallControl'
import VersionInfo from './VersionInfo'

interface Props {
  /** Sheet context: start expanded (the user opened the tab intentionally). */
  defaultOpen?: boolean
}

/** Collapsible settings container — currently holds the "My home" section. */
export default function SettingsPanel({ defaultOpen = false }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(
    () => safeGet(STORAGE_KEYS.settingsOpen) === '1' || defaultOpen,
  )

  const toggle = () => {
    safeSet(STORAGE_KEYS.settingsOpen, open ? '0' : '1')
    setOpen(!open)
  }

  return (
    <div className="panel">
      <button
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 p-3 text-left"
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal size={14} className="text-phosphor-soft/80" />
          <span className="panel-title">{t('settings.title')}</span>
        </span>
        <ChevronDown
          size={14}
          className={`text-slate-500 transition-transform duration-300 ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Smooth auto-height via the grid-rows 0fr -> 1fr trick. */}
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-out ${
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-3">
            <HomeControl />
            <InstallControl />
            <VersionInfo />
          </div>
        </div>
      </div>
    </div>
  )
}
