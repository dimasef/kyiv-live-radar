import { Type } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import type { FeedTextSize } from '../../store/prefsSlice'

const OPTIONS: FeedTextSize[] = ['sm', 'md', 'lg']

/** Event-feed text scale (3 steps), persisted like the sheet height. */
export default function FeedTextControl() {
  const { t } = useTranslation()
  const feedTextSize = useRadar((s) => s.feedTextSize)
  const setFeedTextSize = useRadar((s) => s.setFeedTextSize)

  return (
    <div className="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="mb-2.5 flex items-center gap-2">
        <Type size={13} className="text-phosphor-soft/80" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {t('settings.feedText')}
        </span>
      </div>
      <div className="flex gap-1">
        {OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => setFeedTextSize(opt)}
            aria-pressed={feedTextSize === opt}
            className={`flex-1 rounded-lg px-3 py-1.5 font-medium transition-colors duration-200 ${
              opt === 'sm' ? 'text-xs' : opt === 'md' ? 'text-[13px]' : 'text-[15px]'
            } ${
              feedTextSize === opt
                ? 'border border-phosphor/30 bg-phosphor/15 text-phosphor-soft'
                : 'border border-transparent bg-white/[0.04] text-slate-400'
            }`}
          >
            {t(`settings.feedTextSize.${opt}`)}
          </button>
        ))}
      </div>
    </div>
  )
}
