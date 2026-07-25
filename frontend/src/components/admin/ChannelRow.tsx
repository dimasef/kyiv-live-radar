import type { Source } from '@/api'

import ScoreBadge from './ScoreBadge'
import SourceActions from './SourceActions'
import SourceHeader from './SourceHeader'
import { formatKyivTime, pct } from './sourceFormat'

/** A spotter channel — full quality stats + the score badge (hover for the
 * breakdown). Editing lives in the modal opened from SourceActions. */
export default function ChannelRow({
  source,
  onUpdated,
  onDeleted,
}: {
  source: Source
  onUpdated: (s: Source) => void
  onDeleted: (id: number) => void
}) {
  const st = source.stats

  return (
    <li className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <SourceHeader source={source} />
        <div className="ml-auto">
          <SourceActions source={source} onUpdated={onUpdated} onDeleted={onDeleted} />
        </div>
      </div>

      {source.last_listener_error && (
        <p className="mt-1.5 text-[11px] text-rose-300">⚠ {source.last_listener_error}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-slate-400">
        <ScoreBadge stats={st} />
        <span>
          {st.messages_total} повідомл. ({st.messages_processed} обробл.)
        </span>
        <span>{st.events_produced} подій</span>
        <span title="частка повідомлень каналу, які вдалось прив'язати до карти">
          покриття {pct(st.coverage_rate)}
        </span>
        <span title="частка викликів LLM-фолбеку">LLM {pct(st.llm_fallback_rate)}</span>
        <span title="частка виправлень парсера">помилки {pct(st.correction_rate)}</span>
        <span title="частка подій у конфліктних треках">конфл. {pct(st.conflict_share)}</span>
      </div>

      <div className="mt-2 text-[11px] text-slate-500">
        останнє: {formatKyivTime(st.last_message_at)} · вага довіри: {source.trust_weight}
      </div>
    </li>
  )
}
