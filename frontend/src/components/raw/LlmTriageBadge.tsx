import type { LlmCategory } from '@/types'

/** Dev-only chip showing the LLM's triage category for a message, with a ring
 * when the model flagged it surface-worthy (worth showing an operator even
 * with no district). Stage 1 is audit-only — this does not affect the product
 * feed; it just makes the collected triage visible on /raw. */

const CATEGORY_STYLE: Record<LlmCategory, { label: string; className: string }> = {
  localized: { label: 'локальне', className: 'bg-emerald-400/15 text-emerald-300' },
  citywide: { label: 'на місто', className: 'bg-amber-400/15 text-amber-300' },
  directional: { label: 'напрямок', className: 'bg-sky-400/15 text-sky-300' },
  forecast: { label: 'прогноз', className: 'bg-violet-400/15 text-violet-300' },
  status: { label: 'статус', className: 'bg-slate-400/15 text-slate-300' },
  noise: { label: 'шум', className: 'bg-white/[0.06] text-slate-500' },
}

export default function LlmTriageBadge({
  category,
  surface,
}: {
  category: LlmCategory
  surface: boolean
}) {
  const style = CATEGORY_STYLE[category] ?? CATEGORY_STYLE.noise
  return (
    <span
      className={`flex items-center gap-1 rounded px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight ${style.className} ${
        surface ? 'ring-1 ring-phosphor/50' : ''
      }`}
      title={surface ? 'surface-worthy: варте показу оператору' : undefined}
    >
      {style.label}
      {surface && <span className="text-phosphor">●</span>}
    </span>
  )
}
