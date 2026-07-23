import { Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { AuthButton } from '@/components/auth'
import { MAP_PATH, navigate, useRoute } from '@/router'
import { useRadar } from '@/store'

import { NAV_DESTINATIONS } from './navDestinations'

/** Renders the wordmark with "Live" in the phosphor accent, split from the
 * localized title so it stays a single source of truth. */
function BrandTitle({ text }: { text: string }) {
  return (
    <>
      {text.split(/(Live)/i).map((part, i) =>
        part.toLowerCase() === 'live' ? (
          <span key={i} className="text-phosphor-soft">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  )
}

// Shared control shape for every bar button: a 34×34 icon on mobile, expanding
// to an icon+label pill from lg up. Same idle background as the settings button.
const ctrlBase =
  'flex h-[40px] w-[40px] flex-none items-center justify-center rounded-full border text-[12px] font-medium transition-colors lg:w-auto lg:justify-start lg:gap-1.5 lg:px-3'
const ctrlIdle =
  'border-white/10 bg-white/[0.04] text-slate-400 hover:border-white/20 hover:text-slate-100'

// Page tabs: bare icon-over-label on mobile (no button chrome), a pill on lg up.
const navBase =
  'flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium leading-none transition-colors lg:h-[40px] lg:flex-row lg:gap-1.5 lg:rounded-full lg:border lg:px-3.5 lg:text-[12px]'
const navActive = 'text-phosphor-soft lg:border-phosphor/30 lg:bg-phosphor/15'
const navIdle =
  'text-slate-400 hover:text-slate-100 lg:border-white/10 lg:bg-white/[0.04] lg:hover:border-white/20'

/** The persistent top bar (all routes): brand, navigation (icons on mobile,
 * icon+label on desktop), the settings-drawer trigger, and the auth chip. The
 * connection status lives on the map corner, not here. */
export default function TopBar() {
  const { t } = useTranslation()
  const route = useRoute()
  const isAdmin = useRadar((s) => s.user?.role === 'admin')
  const setSettingsOpen = useRadar((s) => s.setSettingsOpen)
  const dests = NAV_DESTINATIONS.filter((d) => !d.adminOnly || isAdmin)

  return (
    <header className="relative z-[1200] grid flex-none grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-white/5 bg-ink-900/70 px-3 py-2.5 backdrop-blur-xl sm:gap-3 sm:px-4">
      <button
        onClick={() => navigate(MAP_PATH)}
        className="flex min-w-0 items-center gap-2.5 justify-self-start"
        aria-label={t('nav.map')}
      >
        <img src="/favicon.svg" alt="" aria-hidden className="h-9 w-9 flex-none sm:h-10 sm:w-10" />
        {/* Mobile shows the mark alone; the wordmark appears from sm up. */}
        <div className="sr-only min-w-0 text-left sm:not-sr-only sm:block">
          <h1 className="truncate font-display text-[13px] font-bold leading-tight tracking-wide text-slate-100 sm:text-[15px]">
            <BrandTitle text={t('app.title')} />
          </h1>
          <p className="truncate text-[11px] text-slate-400">{t('app.subtitle')}</p>
        </div>
      </button>

      {/* Navigation — bare icon+label on mobile, pills from lg up. Centered in
          the bar via the grid's 1fr side columns. */}
      <nav className="flex items-center gap-6 justify-self-center sm:gap-3">
        {dests.map((d) => {
          const active = route === d.path
          const Icon = d.icon
          return (
            <button
              key={d.key}
              onClick={() => navigate(d.path)}
              aria-current={active ? 'page' : undefined}
              title={t(d.labelKey)}
              className={`${navBase} ${active ? navActive : navIdle}`}
            >
              <Icon size={18} className="flex-none lg:h-3.5 lg:w-3.5" />
              <span className="whitespace-nowrap">{t(d.labelKey)}</span>
            </button>
          )
        })}
      </nav>

      <div className="flex items-center gap-2 justify-self-end sm:gap-3">
        <button
          onClick={() => setSettingsOpen(true)}
          className={`${ctrlBase} ${ctrlIdle}`}
          title={t('nav.settings')}
          aria-label={t('nav.settings')}
        >
          <Settings size={16} className="flex-none" />
          <span className="hidden lg:inline">{t('nav.settings')}</span>
        </button>
        <AuthButton />
      </div>
    </header>
  )
}
