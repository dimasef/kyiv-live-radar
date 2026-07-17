import { Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { riseDelay } from '@/lib/motion'
import { useRadar } from '@/store'

import LanguageSwitcher from './LanguageSwitcher'
import TelegramIcon from './TelegramIcon'

export default function Header() {
  const { t } = useTranslation()
  const feedOk = useRadar((s) => s.feedOk)
  const online = useRadar((s) => s.online)

  return (
    <header
      className="rise relative z-[1200] flex items-center justify-between gap-3 px-3 sm:px-4 py-2.5 border-b border-white/5 bg-ink-900/70 backdrop-blur-xl"
      style={riseDelay(0)}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="radar radar--rings w-9 h-9 sm:w-10 sm:h-10" aria-hidden />
        <div className="min-w-0">
          <h1 className="font-display font-bold text-[13px] sm:text-[15px] tracking-wide text-slate-100 leading-tight truncate">
            {t('app.title')}
          </h1>
          <p className="hidden sm:block text-[11px] text-slate-400 truncate">
            {t('app.subtitle')}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        {online != null && online > 0 && (
          <span
            className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-mono tabular-nums text-slate-300"
            title={t('presence.watching')}
          >
            <Eye size={13} className="flex-none text-phosphor-soft" />
            {online}
          </span>
        )}
        {feedOk === false && (
          <span
            className="flex items-center gap-2 rounded-full border border-red-400/25 bg-red-400/5 px-2.5 py-1 text-[11px] font-mono text-red-300"
            title={t('conn.feedUnavailable')}
          >
            <TelegramIcon size={12} className="flex-none" />
            <span className="hidden md:inline">{t('conn.feedUnavailable')}</span>
          </span>
        )}
        <LanguageSwitcher />
      </div>
    </header>
  )
}
