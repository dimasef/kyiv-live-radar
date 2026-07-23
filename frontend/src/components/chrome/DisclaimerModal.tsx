import { ExternalLink, TriangleAlert, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useDismissTransition } from '@/lib/useDismissTransition'

import { safeSet, STORAGE_KEYS } from '../../lib/storage'

/** Safety disclaimer as a load-time modal. Mounted only while open (by App), so
 * it animates in and out; "don't show again" only skips the auto-open. */
export default function DisclaimerModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)

  const dontShowAgain = () => {
    safeSet(STORAGE_KEYS.disclaimerHide, '1')
    close()
  }

  return (
    <div
      className={`fixed inset-0 z-[1500] flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      role="dialog"
      aria-modal="true"
      aria-label={t('disclaimer.title')}
      onClick={close}
    >
      <div
        className={`panel relative w-full max-w-md border-amber-500/20 p-5 transition-all duration-200 ease-out sm:p-6 ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={close}
          aria-label={t('disclaimer.dismiss')}
          className="absolute right-3 top-3 rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
        >
          <X size={16} />
        </button>

        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 shadow-[0_0_18px_-4px_rgba(245,158,11,0.5)]">
            <TriangleAlert size={20} />
          </span>
          <h2 className="font-display text-sm font-bold tracking-wide text-slate-100">
            {t('disclaimer.title')}
          </h2>
        </div>

        <p className="mt-4 text-[13px] leading-relaxed text-slate-300">{t('disclaimer.text')}</p>
        <p className="mt-2 text-[13px] font-semibold leading-relaxed text-amber-200">
          {t('disclaimer.never')}
        </p>

        <a
          href="https://alerts.in.ua"
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-phosphor-soft underline decoration-phosphor/40 underline-offset-2 transition-colors hover:text-phosphor"
        >
          {t('sources.alerts')}
          <ExternalLink size={13} />
        </a>

        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button onClick={dontShowAgain} className="btn text-slate-400">
            {t('disclaimer.dontShow')}
          </button>
          <button onClick={close} className="btn btn--warn font-semibold">
            {t('disclaimer.dismiss')}
          </button>
        </div>
      </div>
    </div>
  )
}
