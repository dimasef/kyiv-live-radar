import type { RawOutcomeFilter, RawSource, Region } from '@/types'

import type { RawMessageFilters } from './useRawMessages'

/** Every filter in its off position — what «Скинути» restores, and the baseline
 * a URL is read against (a param absent from the URL is this). */
export const NO_RAW_FILTERS: RawMessageFilters = {
  q: '',
  outcome: 'all',
  llm: 'all',
  sourceIds: [],
  regions: [],
}

export function hasActiveFilters(f: RawMessageFilters): boolean {
  return (
    f.q !== '' ||
    f.outcome !== 'all' ||
    f.llm !== 'all' ||
    f.sourceIds.length > 0 ||
    f.regions.length > 0
  )
}

const OUTCOMES: readonly (RawOutcomeFilter | 'all')[] = ['all', 'event', 'suppressed']
const LLMS = ['all', 'yes', 'no'] as const

/** Filters -> query string, off positions omitted. The URL is the shareable
 * form of a filter: an export or a bug report can point at the exact slice that
 * produced it, and a reload keeps what the operator was looking at. */
export function filtersToSearch(f: RawMessageFilters): string {
  const p = new URLSearchParams()
  if (f.q) p.set('q', f.q)
  if (f.outcome !== 'all') p.set('outcome', f.outcome)
  if (f.llm !== 'all') p.set('llm', f.llm)
  if (f.sourceIds.length) p.set('sources', f.sourceIds.join(','))
  if (f.regions.length) p.set('regions', f.regions.join(','))
  return p.toString()
}

/** Query string -> filters, ignoring anything it doesn't recognise: the URL is
 * user-editable, so a garbled param falls back to that filter's off position
 * rather than to an empty screen with nothing explaining it.
 *
 * Region ids are the one value not checked against a list — the frontend has no
 * runtime enum of them (`Region` is a generated type) and the catalogue arrives
 * asynchronously, so the shape is checked here and the server stays the
 * authority, exactly as it is for every other query param.
 */
export function filtersFromSearch(search: string): RawMessageFilters {
  const p = new URLSearchParams(search)
  const outcome = p.get('outcome') as RawOutcomeFilter | 'all' | null
  const llm = p.get('llm') as (typeof LLMS)[number] | null
  return {
    q: p.get('q')?.trim() || '',
    outcome: outcome && OUTCOMES.includes(outcome) ? outcome : 'all',
    llm: llm && LLMS.includes(llm) ? llm : 'all',
    sourceIds: list(p.get('sources'))
      .map(Number)
      .filter((n) => Number.isInteger(n) && n > 0),
    regions: list(p.get('regions')).filter((r) => /^[a-z_]{2,}$/.test(r)) as Region[],
  }
}

function list(raw: string | null): string[] {
  return (raw ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

/** The sources worth offering while `regions` are picked: the channels BOUND to
 * one of them (primary or extra — `RawSourceOut.regions`).
 *
 * Bindings, not where a message landed: a source never pins a place outside
 * them, so they are exactly the set of channels that can produce anything in
 * the picked oblasts. An empty pick is the filter's off position and offers
 * everything.
 */
export function sourcesInRegions(sources: RawSource[], regions: Region[]): RawSource[] {
  if (regions.length === 0) return sources
  return sources.filter((s) => s.regions.some((r) => regions.includes(r)))
}
