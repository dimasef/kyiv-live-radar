import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import { typeLabel } from '../../threatDisplay'
import { threatColor } from '../../theme'

/** Floating pill showing which track is being inspected, with a close button
 * — the explicit way out of inspection (besides re-clicking the same feed
 * item), since the feed panel and map can be scrolled apart on mobile. Lives
 * in the same top-center stack as the StatusBanner, so it flows below it. */
export default function InspectBadge() {
  const { t } = useTranslation()
  const inspected = useRadar((s) => s.inspectedThreat)
  const liveThreats = useRadar((s) => s.threats)
  const clearInspection = useRadar((s) => s.clearInspection)

  if (!inspected) return null

  const display = liveThreats[inspected.id] ?? inspected
  const color = threatColor(display)

  return (
    <div className="panel pointer-events-auto flex items-center gap-2.5 px-3 py-1.5">
      <span
        className="h-2.5 w-2.5 flex-none rounded-full"
        style={{ background: color, boxShadow: `0 0 8px ${color}66` }}
      />
      <span className="whitespace-nowrap text-xs text-slate-200">
        {t('inspect.viewing')}{' '}
        <span className="font-medium text-slate-100">{typeLabel(display, t)}</span>
        {display.events.length > 0 && (
          <span className="ml-1.5 font-mono text-[10px] text-slate-500">
            · {display.events.length} {t('inspect.events')}
          </span>
        )}
      </span>
      <button
        onClick={clearInspection}
        aria-label={t('inspect.close')}
        title={t('inspect.close')}
        className="ml-1 flex h-5 w-5 flex-none items-center justify-center rounded-full text-slate-400 transition-colors duration-200 hover:bg-white/10 hover:text-slate-100"
      >
        <X size={13} />
      </button>
    </div>
  )
}
