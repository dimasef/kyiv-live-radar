import type { Source } from '@/api'

import SourceActions from './SourceActions'
import SourceHeader from './SourceHeader'
import { formatKyivTime } from './sourceFormat'

/** An alert channel — no map/quality stats (it feeds the air-raid parser, not
 * the map), so only the essentials: liveness, volume, last message. */
export default function AlertRow({
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

      <div className="mt-2 text-[11px] text-slate-500">
        {st.messages_total} повідомл. · останнє: {formatKyivTime(st.last_message_at)}
      </div>
    </li>
  )
}
