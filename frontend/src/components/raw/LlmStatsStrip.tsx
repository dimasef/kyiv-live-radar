import { useEffect, useState } from 'react'

import { fetchRawLlmStats } from '@/api'
import type { RawLlmStats } from '@/types'

/** Overall LLM fallback spend across ALL raw messages — unaffected by the
 * page's current search/filter, so it always reads as total spend. */
export default function LlmStatsStrip() {
  const [stats, setStats] = useState<RawLlmStats | null>(null)

  useEffect(() => {
    fetchRawLlmStats().then(setStats).catch(() => {})
  }, [])

  if (!stats || stats.calls === 0) return null

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-violet-400/15 bg-violet-400/[0.04] px-3 py-2 text-[11px] text-slate-400">
      <span className="font-semibold uppercase tracking-wide text-violet-300">LLM усього</span>
      <span>{stats.calls} викликів</span>
      <span>
        {stats.input_tokens.toLocaleString('uk-UA')} + {stats.output_tokens.toLocaleString('uk-UA')} токенів
      </span>
      <span className="font-mono font-semibold text-violet-300">${stats.cost_usd.toFixed(4)}</span>
    </div>
  )
}
