import { Info, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { HOME_COLOR, STATUS_COLORS } from '@/theme'
import type { Notice } from '@/types'

import { DevId, EventTime, SourceBadge } from './badges'

/** An info entry in the feed timeline: an all-clear or an attack summary —
 * important to see, but not a live threat. A multi-source all-clear renders as
 * one card with all its source badges, not one card per channel. */
export default function NoticeCard({ notices }: { notices: Notice[] }) {
  const { t } = useTranslation()
  const head = notices[0]
  const isClear = head.kind === 'clear'
  const color = isClear ? STATUS_COLORS.clear : HOME_COLOR
  const Icon = isClear ? ShieldCheck : Info
  const sources = Array.from(new Set(notices.map((n) => n.source_name).filter(Boolean)))

  return (
    <li
      className="feed-item rounded-lg border px-2.5 py-2 text-xs backdrop-blur-sm"
      style={{
        borderColor: `${color}22`,
        borderLeft: `2px solid ${color}`,
        background: `${color}0d`,
        boxShadow: `inset 2px 0 10px -4px ${color}55`,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className="flex items-center gap-1.5 font-semibold uppercase tracking-wide"
          style={{ color }}
        >
          <Icon size={12} className="flex-none" />
          {t(`notice.${head.kind}`)}
          {notices.length > 1 && (
            <span className="font-mono font-semibold" style={{ color }}>
              ×{notices.length}
            </span>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          <DevId>N{head.id}</DevId>
          <EventTime iso={head.event_time} />
        </span>
      </div>
      <div className="mt-0.5 break-words leading-snug text-slate-300">{head.text}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {sources.length > 0 ? (
          sources.map((name) => <SourceBadge key={name} name={name} t={t} />)
        ) : (
          <SourceBadge name={head.source_name} t={t} />
        )}
      </div>
    </li>
  )
}
