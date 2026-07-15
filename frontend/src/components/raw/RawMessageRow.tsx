import type { RawMessage } from '@/types'

import LlmTriageBadge from './LlmTriageBadge'
import LlmUsageBadge from './LlmUsageBadge'
import OutcomeBadge from './OutcomeBadge'

// Same condition as OutcomeBadge's tone: a real ThreatEvent/Notice matched,
// i.e. this message actually became a card in the main feed (ThreatLog) —
// not just a best-effort "outcome" guess.
function inMainFeed(item: RawMessage) {
  return item.events.length > 0 || item.notice_id != null
}

export default function RawMessageRow({
  item,
  selected,
  onToggleSelect,
}: {
  item: RawMessage
  selected: boolean
  onToggleSelect: (id: number) => void
}) {
  const borderClass = inMainFeed(item)
    ? item.events.length > 0
      ? 'border-emerald-400/40'
      : 'border-sky-400/40'
    : 'border-white/[0.05]'

  return (
    <li
      className={`flex gap-2.5 rounded-lg border ${borderClass} bg-white/[0.02] px-3 py-2.5 text-xs ${
        selected ? 'ring-1 ring-phosphor/50' : ''
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggleSelect(item.id)}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-phosphor"
        aria-label={`Вибрати повідомлення #${item.id}`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
            #{item.id}
            {item.source_name && <span className="text-slate-400">{item.source_name}</span>}
          </span>
          <span className="flex items-center gap-1.5">
            {item.llm_response && (
              <LlmTriageBadge
                category={item.llm_response.category}
                surface={item.llm_response.surface}
              />
            )}
            {item.llm_attempted && (
              <LlmUsageBadge
                inputTokens={item.llm_input_tokens}
                outputTokens={item.llm_output_tokens}
                costUsd={item.llm_cost_usd}
              />
            )}
            <OutcomeBadge outcome={item.outcome} events={item.events} noticeId={item.notice_id} />
            <time className="font-mono text-[10px] tabular-nums text-slate-500">
              {new Date(item.event_time).toLocaleString('uk-UA', { timeZone: 'Europe/Kyiv' })}
            </time>
          </span>
        </div>
        <p className="mt-1.5 whitespace-pre-wrap break-words leading-snug text-slate-300">
          {item.text}
        </p>
        {item.llm_response?.surface && item.llm_response.summary && (
          <p className="mt-1.5 rounded border border-phosphor/25 bg-phosphor/[0.06] px-2 py-1 text-[11px] leading-snug text-phosphor/90">
            {item.llm_response.summary}
          </p>
        )}
      </div>
    </li>
  )
}
