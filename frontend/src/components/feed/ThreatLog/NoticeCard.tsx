import { CloudLightning, Compass, Info, Radio, ShieldCheck, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { HOME_COLOR, STATUS_COLORS, TYPE_COLORS } from '@/theme'
import type { Notice, NoticeKind } from '@/types'

import AllClearCard from './AllClearCard'
import { DevId, EventTime, SourceName } from './badges'
import ClampText from './ClampText'

/** Per-kind icon + accent colour. Rule notices (clear/summary) keep their
 * established look; the LLM-triage context kinds (directional/forecast/status)
 * each get a distinct cue. Unknown kinds fall back to a neutral info card so a
 * backend deployed ahead of the client never renders oddly. */
const STYLE: Record<NoticeKind, { icon: LucideIcon; color: string }> = {
  clear: { icon: ShieldCheck, color: STATUS_COLORS.clear },
  summary: { icon: Info, color: HOME_COLOR },
  directional: { icon: Compass, color: TYPE_COLORS.jet_drone },
  forecast: { icon: CloudLightning, color: TYPE_COLORS.shahed },
  status: { icon: Radio, color: TYPE_COLORS.unknown },
}
const FALLBACK = { icon: Info, color: HOME_COLOR }

/** Every channel behind this card, deduplicated and in the order they appear. */
function sourceNames(notices: Notice[]): string | null {
  const names = [...new Set(notices.map((n) => n.source_name).filter(Boolean))]
  return names.length > 0 ? names.join(' · ') : null
}

/** An info entry in the feed timeline: an all-clear, an attack summary, or an
 * LLM-surfaced context cue (directional / forecast / status). A multi-source
 * unit renders as one card with all its source badges. */
export default function NoticeCard({ notices }: { notices: Notice[] }) {
  const { t } = useTranslation()
  const head = notices[0]
  // The all-clear has a card of its own: it is the only notice that says the
  // raid is OVER, and it is what someone scrolls back to find afterwards.
  if (head.kind === 'clear') return <AllClearCard notices={notices} />
  const { icon: Icon, color } = STYLE[head.kind as NoticeKind] ?? FALLBACK
  const isAi = head.generated_by === 'llm'

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
          {t(`notice.${head.kind}`, head.kind)}
          {notices.length > 1 && (
            <span className="font-mono font-semibold" style={{ color }}>
              ×{notices.length}
            </span>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          {isAi && (
            <span className="flex items-center gap-1 rounded bg-white/[0.06] px-1 py-px text-[9px] font-medium text-slate-400">
              <Sparkles size={9} className="flex-none" />
              {t('notice.ai')}
            </span>
          )}
          <DevId>N{head.id}</DevId>
          <EventTime iso={head.event_time} />
        </span>
      </div>
      <ClampText
        text={head.text}
        className="mt-0.5 break-words leading-snug text-slate-300"
      />
      {/* A clustered cue is the SAME notice seen by several channels, so it
          names all of them — that several agreed is the point of clustering. */}
      <SourceName name={sourceNames(notices)} />
    </li>
  )
}
