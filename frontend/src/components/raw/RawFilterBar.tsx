import type { RawOutcomeFilter, RawSource } from '@/types'

import FilterSelect from './FilterSelect'

const OUTCOME_OPTIONS: { value: RawOutcomeFilter | 'all'; label: string }[] = [
  { value: 'all', label: 'Усі' },
  { value: 'event', label: 'Подія' },
  { value: 'suppressed', label: 'Не подія' },
]

const LLM_OPTIONS: { value: 'all' | 'yes' | 'no'; label: string }[] = [
  { value: 'all', label: 'LLM: усі' },
  { value: 'yes', label: 'LLM: так' },
  { value: 'no', label: 'LLM: ні' },
]

export default function RawFilterBar({
  search,
  onSearchChange,
  outcome,
  onOutcomeChange,
  llm,
  onLlmChange,
  sources,
  sourceId,
  onSourceIdChange,
}: {
  search: string
  onSearchChange: (v: string) => void
  outcome: RawOutcomeFilter | 'all'
  onOutcomeChange: (v: RawOutcomeFilter | 'all') => void
  llm: 'all' | 'yes' | 'no'
  onLlmChange: (v: 'all' | 'yes' | 'no') => void
  sources: RawSource[]
  sourceId: number | 'all'
  onSourceIdChange: (v: number | 'all') => void
}) {
  const sourceOptions: { value: string; label: string }[] = [
    { value: 'all', label: 'Усі канали' },
    ...sources.map((s) => ({ value: String(s.id), label: s.name })),
  ]

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <input
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Пошук у тексті, або T217 / N82 / M668…"
        className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:border-phosphor/40 focus:outline-none"
      />
      <FilterSelect
        options={sourceOptions}
        value={sourceId === 'all' ? 'all' : String(sourceId)}
        onChange={(v) => onSourceIdChange(v === 'all' ? 'all' : Number(v))}
      />
      <FilterSelect options={OUTCOME_OPTIONS} value={outcome} onChange={onOutcomeChange} />
      <FilterSelect options={LLM_OPTIONS} value={llm} onChange={onLlmChange} />
    </div>
  )
}
