import { TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import { CorroborationLine, CountBadge, typeLabel } from '@/threatDisplay'
import { threatColor } from '@/theme'
import type { FeedEntry } from '@/types'

import { DevId, DevSource, EventTime, SourceBadge } from './badges'
import StatusChip from './StatusChip'
import TypeGlyph from './TypeGlyph'

/** One live sighting — the feed's main card. Click toggles map inspection. */
export default function ThreatCard({ event, threat }: FeedEntry) {
  const { t } = useTranslation()
  const isSelected = useRadar((s) => s.inspectedThreat?.id === threat.id)
  const inspectThreat = useRadar((s) => s.inspectThreat)
  const clearInspection = useRadar((s) => s.clearInspection)

  const color = threatColor(threat)
  const toggleInspect = () => (isSelected ? clearInspection() : inspectThreat(threat))

  return (
    <li
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onClick={toggleInspect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          toggleInspect()
        }
      }}
      className={`feed-item cursor-pointer rounded-lg border px-2.5 py-2 text-xs backdrop-blur-sm transition-colors duration-200 ${
        isSelected
          ? 'border-white/20 bg-white/[0.09]'
          : 'border-white/[0.05] bg-white/[0.03] hover:bg-white/[0.06]'
      }`}
      style={{
        borderLeft: `2px solid ${color}`,
        boxShadow: isSelected
          ? `inset 2px 0 8px -4px ${color}55, 0 0 0 1px ${color}55`
          : `inset 2px 0 8px -4px ${color}55`,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5 font-medium text-slate-100">
          <TypeGlyph threat={threat} />
          <StatusChip threat={threat} />
          {typeLabel(threat, t)}
          {/* Count KNOWN AS OF this event (running-max at the time), not
              the track's final count — so an early "Ціль на місто!"
              doesn't retroactively show the ×3 that only a later "3
              ракети" established. Fall back to the track's current count
              for pre-column events (null). */}
          <CountBadge
            count={event.event_target_count ?? threat.target_count}
            className="ml-1 font-mono font-semibold text-amber-400"
          />
        </span>
        <span className="flex items-center gap-1.5">
          <DevId>
            T{threat.id}/M{event.id}
          </DevId>
          <DevSource source={event.decision_source} />
          <EventTime iso={event.event_time} />
        </span>
      </div>

      <div className="mt-0.5 break-words leading-snug text-slate-300">{event.raw_text}</div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <SourceBadge name={event.source_name} t={t} />
        <CorroborationLine
          threat={threat}
          className="font-mono text-[10px] tabular-nums text-slate-500"
        />
        {threat.has_conflict && (
          <span className="flex items-center gap-1 text-[10px] font-medium text-orange-400">
            <TriangleAlert size={10} className="flex-none" />
            {t('log.conflict')}
          </span>
        )}
      </div>
    </li>
  )
}
