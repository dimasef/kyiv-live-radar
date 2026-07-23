import { X } from 'lucide-react'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { useDismissTransition } from '@/lib/useDismissTransition'
import { useRadar } from '@/store'

import FeedSettings from './FeedSettings'
import HomeControl from './HomeControl'
import InstallControl from './InstallControl'
import LanguageSwitcher from './LanguageSwitcher'
import NotifyControl from './NotifyControl'
import VersionInfo from './VersionInfo'

/** App settings, lifted out of the map's side panel into a slide-in drawer that
 * works identically on every route: a bottom sheet on mobile, a right-hand panel
 * on desktop. Opened from the TopBar gear; closes on backdrop / X / Esc. Hosts
 * the language switcher (moved here) plus the setting controls. */
function DrawerBody({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex justify-end bg-ink-950/70 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`ml-auto flex h-full w-full max-w-md flex-col border-l border-white/10 bg-ink-900 shadow-2xl transition-transform duration-300 ease-out max-lg:mt-auto max-lg:h-[86dvh] max-lg:max-w-full max-lg:rounded-t-2xl max-lg:border-l-0 max-lg:border-t ${
          shown
            ? 'translate-y-0 lg:translate-x-0'
            : 'translate-y-full lg:translate-y-0 lg:translate-x-full'
        }`}
      >
        <div className="flex flex-none items-center justify-between border-b border-white/5 px-4 py-3">
          <h2 className="font-display text-sm font-bold text-slate-100">{t('nav.settings')}</h2>
          <button
            onClick={close}
            aria-label={t('panel.close')}
            className="text-slate-400 transition-colors hover:text-slate-100"
          >
            <X size={18} />
          </button>
        </div>

        <div className="scroll-slim flex-1 overflow-y-auto px-3 py-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5">
            <span className="panel-title">{t('settings.language')}</span>
            <LanguageSwitcher />
          </div>
          <HomeControl />
          <NotifyControl />
          <FeedSettings />
          <InstallControl />
          <VersionInfo />
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default function SettingsDrawer() {
  const open = useRadar((s) => s.settingsOpen)
  const setOpen = useRadar((s) => s.setSettingsOpen)
  if (!open) return null
  return <DrawerBody onClose={() => setOpen(false)} />
}
