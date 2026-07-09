import { RadioTower, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../store'
import { threatColor } from '../theme'

export default function ThreatLog() {
  const { t } = useTranslation()
  const log = useRadar((s) => s.log)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="panel-title mb-2 hidden lg:block">{t('log.title')}</div>

      {log.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
          <div className="radar radar--rings h-16 w-16 opacity-70" aria-hidden />
          <div className="font-mono text-xs text-slate-500">{t('log.empty')}</div>
        </div>
      ) : (
        <ul className="scroll-slim min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {log.map(({ event, threat }) => {
            const color = threatColor(threat)
            return (
              <li
                key={event.id}
                className="feed-item rounded-lg border border-white/[0.05] bg-white/[0.03] px-2.5 py-2 text-xs backdrop-blur-sm transition-colors duration-200 hover:bg-white/[0.06]"
                style={{
                  borderLeft: `2px solid ${color}`,
                  boxShadow: `inset 2px 0 8px -4px ${color}55`,
                }}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-100">
                    {t(`target.${threat.target_type}`)}
                    {threat.target_count > 1 && (
                      <span className="ml-1 font-mono font-semibold text-amber-300">
                        ×{threat.target_count}
                      </span>
                    )}
                  </span>
                  <span className="font-mono text-[10px] tabular-nums text-slate-500">
                    {new Date(event.event_time).toLocaleTimeString()}
                  </span>
                </div>

                <div className="mt-0.5 break-words leading-snug text-slate-300">
                  {event.raw_text}
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span
                    className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] ${
                      event.source_name
                        ? 'bg-white/[0.06] text-slate-300'
                        : 'bg-white/[0.03] italic text-slate-500'
                    }`}
                  >
                    <RadioTower size={10} className="flex-none opacity-70" />
                    {event.source_name ?? t('log.unknownSource')}
                  </span>
                  <span className="font-mono text-[10px] tabular-nums text-slate-500">
                    {threat.corroboration_count} {t('log.corroboration')} ·{' '}
                    {Math.round(threat.confidence * 100)}% {t('log.confidence')}
                  </span>
                  {threat.has_conflict && (
                    <span className="flex items-center gap-1 text-[10px] font-medium text-orange-400">
                      <TriangleAlert size={10} className="flex-none" />
                      {t('log.conflict')}
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
