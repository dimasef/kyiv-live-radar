import { useRadar } from '@/store'
import type { RawOutcomeFilter, RawSource, Region } from '@/types'

import FilterMultiSelect from './FilterMultiSelect'
import FilterSelect from './FilterSelect'
import { sourcesInRegions } from './rawFilters'

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
  sourceIds,
  onSourceIdsChange,
  regions: pickedRegions,
  onRegionsChange,
}: {
  search: string
  onSearchChange: (v: string) => void
  outcome: RawOutcomeFilter | 'all'
  onOutcomeChange: (v: RawOutcomeFilter | 'all') => void
  llm: 'all' | 'yes' | 'no'
  onLlmChange: (v: 'all' | 'yes' | 'no') => void
  sources: RawSource[]
  sourceIds: number[]
  onSourceIdsChange: (v: number[]) => void
  regions: Region[]
  onRegionsChange: (v: Region[]) => void
}) {
  // From the server catalogue, so a newly declared region is filterable the day
  // it exists — and one with no coverage yet is still offered, because "did
  // anything reach us from there" is a fair question to ask of an empty region.
  const catalogue = useRadar((s) => s.regions)
  // The regions steer the sources: with an oblast picked, the list offers only
  // the channels bound to it. Picking a region also drops any already-picked
  // source that isn't — otherwise the two filters would AND into a guaranteed
  // empty result with nothing on screen explaining why.
  const offeredSources = sourcesInRegions(sources, pickedRegions)

  const pickRegions = (next: Region[]) => {
    onRegionsChange(next)
    const stillOffered = new Set(sourcesInRegions(sources, next).map((s) => s.id))
    const kept = sourceIds.filter((id) => stillOffered.has(id))
    if (kept.length !== sourceIds.length) onSourceIdsChange(kept)
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <input
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Пошук у тексті, або T217 / N82 / M668…"
        className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:border-phosphor/40 focus:outline-none"
      />
      <FilterMultiSelect
        options={catalogue.map((r) => ({
          value: r.id,
          label: r.name_uk,
          muted: !r.active,
        }))}
        value={pickedRegions}
        allLabel="Усі області"
        onChange={(next) => pickRegions(next as Region[])}
      />
      <FilterMultiSelect
        options={offeredSources.map((s) => ({ value: s.id, label: s.name }))}
        value={sourceIds}
        allLabel="Усі джерела"
        noneLabel="Немає джерел в обраних областях"
        onChange={onSourceIdsChange}
      />
      <FilterSelect options={OUTCOME_OPTIONS} value={outcome} onChange={onOutcomeChange} />
      <FilterSelect options={LLM_OPTIONS} value={llm} onChange={onLlmChange} />
    </div>
  )
}
