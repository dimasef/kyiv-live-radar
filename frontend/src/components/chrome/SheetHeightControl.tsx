import { PanelBottom } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import type { SheetHeight } from '../../store/prefsSlice'

const OPTIONS: SheetHeight[] = ['low', 'mid', 'high']

/** Mobile-only setting: how far the event-feed bottom sheet opens (3 steps).
 * Hidden on desktop (lg:hidden), where the feed lives in a fixed sidebar. */
export default function SheetHeightControl() {
  const { t } = useTranslation()
  const sheetHeight = useRadar((s) => s.sheetHeight)
  const setSheetHeight = useRadar((s) => s.setSheetHeight)

  return (
    <div className="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3 lg:hidden">
      <div className="mb-2.5 flex items-center gap-2">
        <PanelBottom size={13} className="text-phosphor-soft/80" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {t('settings.sheetHeight')}
        </span>
      </div>
      <div className="flex gap-1">
        {OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => setSheetHeight(opt)}
            aria-pressed={sheetHeight === opt}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
              sheetHeight === opt
                ? 'border border-phosphor/30 bg-phosphor/15 text-phosphor-soft'
                : 'border border-transparent bg-white/[0.04] text-slate-400'
            }`}
          >
            {t(`settings.sheet.${opt}`)}
          </button>
        ))}
      </div>
    </div>
  )
}
