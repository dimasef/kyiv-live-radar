import { CalendarClock, Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { AuthButton } from '@/components/auth'
import { riseDelay } from '@/lib/motion'
import { navigate, THREAT_JOURNAL_PATH } from '@/router'
import { useRadar } from '@/store'

import LanguageSwitcher from './LanguageSwitcher'
import TelegramIcon from './TelegramIcon'

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
        <img
          src="/favicon.svg"
          alt=""
          aria-hidden
          className="w-9 h-9 sm:w-10 sm:h-10 flex-none"
        />
        {/* Mobile shows the mark alone; the wordmark appears from sm up. */}
        <div className="sr-only sm:not-sr-only sm:block min-w-0">
          <h1 className="font-display font-bold text-[13px] sm:text-[15px] tracking-wide text-slate-100 leading-tight truncate">
            <BrandTitle text={t('app.title')} />
          </h1>
          <p className="text-[11px] text-slate-400 truncate">{t('app.subtitle')}</p>
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
        <a
          href={THREAT_JOURNAL_PATH}
          onClick={(e) => {
            e.preventDefault()
            navigate(THREAT_JOURNAL_PATH)
          }}
          className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] p-1.5 text-slate-400 transition-colors hover:border-white/20 hover:text-phosphor-soft md:px-2.5 md:py-1"
          title={t('journal.title')}
          aria-label={t('journal.title')}
        >
          <CalendarClock size={16} className="flex-none md:h-[13px] md:w-[13px]" />
          {/* Mobile keeps the icon alone; the label appears from md up. */}
          <span className="hidden font-mono text-[11px] md:inline">{t('journal.short')}</span>
        </a>
        <AuthButton />
        <LanguageSwitcher />
      </div>
    </header>
  )
}
