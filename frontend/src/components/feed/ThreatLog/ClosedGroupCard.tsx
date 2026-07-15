import { CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import { STATUS_COLORS, threatColor } from '@/theme'
import type { FeedEntry } from '@/types'

import { DevId, DevSource, EventTime, SourceBadge } from './badges'

/** Several tracks closed by ONE real message ("дорозвідка" with no stated
 * type closes every open track at once) — one card, one clickable chip per
 * closed track so each can still be inspected. Green accent (same as
 * legend.clear) — this is good news, resolved/closed tracks, not a sighting. */
export default function ClosedGroupCard({ group }: { group: FeedEntry[] }) {
  const { t } = useTranslation()
  const districts = useRadar((s) => s.districts)
  const inspectedId = useRadar((s) => s.inspectedThreat?.id)
  const inspectThreat = useRadar((s) => s.inspectThreat)
  const clearInspection = useRadar((s) => s.clearInspection)
  const head = group[0]
  const closedColor = STATUS_COLORS.clear

  return (
    <li
      className="feed-item rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] px-2.5 py-2 text-xs backdrop-blur-sm"
      style={{
        borderLeft: `2px solid ${closedColor}`,
        boxShadow: `inset 2px 0 10px -4px ${closedColor}55`,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5 font-medium text-emerald-300">
          <CheckCircle2 size={12} className="flex-none" />
          {t('log.closedMultiple')}
          <span className="font-mono font-semibold text-emerald-200">×{group.length}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <DevId>M{head.event.id}</DevId>
          <DevSource source={head.event.decision_source} />
          <EventTime iso={head.event.event_time} />
        </span>
      </div>

      <div className="mt-0.5 break-words leading-snug text-slate-300">{head.event.raw_text}</div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {group.map(({ event, threat }) => {
          const color = threatColor(threat)
          const districtName = districts.find((d) => d.id === event.district_id)?.name_uk ?? '?'
          const isSelected = inspectedId === threat.id
          return (
            <button
              key={event.id}
              onClick={() => (isSelected ? clearInspection() : inspectThreat(threat))}
              className="rounded-md px-1.5 py-0.5 text-[10px] font-medium transition-shadow duration-200"
              style={{
                background: `${color}22`,
                color,
                boxShadow: isSelected ? `0 0 0 1px ${color}` : undefined,
              }}
            >
              {districtName}
              {import.meta.env.DEV && <span className="ml-1 opacity-70">T{threat.id}</span>}
            </button>
          )
        })}
      </div>

      <div className="mt-1.5">
        <SourceBadge name={head.event.source_name} t={t} />
      </div>
    </li>
  )
}
