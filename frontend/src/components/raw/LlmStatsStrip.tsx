import { useEffect, useState } from 'react'

import { fetchRawLlmStats } from '@/api'
import type { RawLlmStats } from '@/types'

/** Amber/orange as spend nears the cap — the same escalation `llm_spend_ok`
 * uses to decide when to fall back to rules-only, so the color means
 * something rather than just decorating a bar. */
function barColor(fraction: number) {
  if (fraction >= 1) return 'bg-orange-400'
  if (fraction >= 0.8) return 'bg-amber-400'
  return 'bg-violet-400/70'
}

/** One budget bar; hidden entirely when its cap is 0 (unlimited), since
 * there's nothing to show progress against. */
function BudgetBar({ label, spend, cap }: { label: string; spend: number; cap: number }) {
  if (cap <= 0) return null
  const fraction = Math.min(spend / cap, 1)
  return (
    <div className="min-w-[7rem] flex-1">
      <div className="flex items-baseline justify-between gap-2 text-[10px] text-slate-500">
        <span>{label}</span>
        <span className="font-mono text-slate-400">
          ${spend.toFixed(2)} / ${cap.toFixed(2)}
        </span>
      </div>
      <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={`h-full rounded-full ${barColor(fraction)}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
    </div>
  )
}

/** Overall LLM fallback spend across ALL raw messages — unaffected by the
 * page's current search/filter, so it always reads as total spend — plus
 * today's/this month's spend against the running budget caps that gate the
 * live fallback (see `pipeline.triage.llm_spend_ok`). */
export default function LlmStatsStrip() {
  const [stats, setStats] = useState<RawLlmStats | null>(null)

  useEffect(() => {
    fetchRawLlmStats().then(setStats).catch(() => {})
  }, [])

  if (!stats || stats.calls === 0) return null

  return (
    <div className="mt-3 rounded-lg border border-violet-400/15 bg-violet-400/[0.04] px-3 py-2 text-[11px] text-slate-400">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-violet-300">LLM усього</span>
        <span>{stats.calls} викликів</span>
        <span>
          {stats.input_tokens.toLocaleString('uk-UA')} + {stats.output_tokens.toLocaleString('uk-UA')}{' '}
          токенів
        </span>
        <span className="font-mono font-semibold text-violet-300">${stats.cost_usd.toFixed(4)}</span>
      </div>
      {(stats.day_budget_usd > 0 || stats.month_budget_usd > 0) && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
          <BudgetBar label="Сьогодні" spend={stats.day_spend_usd} cap={stats.day_budget_usd} />
          <BudgetBar label="Цей місяць" spend={stats.month_spend_usd} cap={stats.month_budget_usd} />
        </div>
      )}
    </div>
  )
}
