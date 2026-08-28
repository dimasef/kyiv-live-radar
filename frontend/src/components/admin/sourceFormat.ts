import type { Source, SourceStats } from '@/api'
import { kyivStamp } from '@/lib/kyivTime'
import type { RegionInfo } from '@/types'

/** Pure formatting/derivation helpers for the Sources admin tab (kept out of the
 * JSX so they're trivially testable and the row components stay lean). */

export const pct = (v: number | null): string => (v == null ? '—' : `${Math.round(v * 100)}%`)

export interface RegionGroup {
  region: RegionInfo
  sources: Source[]
}

/** Split a role tab's sources into per-region blocks, in catalogue order.
 *
 * Empty groups are dropped EXCEPT the home one: five headers over one channel
 * is a table of contents, not a grouping. Which regions exist is discoverable
 * from the add form's picker instead.
 *
 * Order within a group is preserved — the server already sorts by
 * (inactive last, name), and re-sorting here would quietly diverge from it.
 * Falls back to one unlabelled group while the catalogue is still loading, so
 * the list renders rather than blanking.
 */
export function groupSourcesByRegion(
  sources: Source[],
  catalogue: RegionInfo[],
): RegionGroup[] {
  if (catalogue.length === 0) return []
  return catalogue
    .map((region) => ({ region, sources: sources.filter((s) => s.region === region.id) }))
    .filter((group) => group.region.is_home || group.sources.length > 0)
}

/** Tailwind text-color band for the 0..100 quality score. */
export const scoreColor = (score: number | null): string => {
  if (score == null) return 'text-slate-500'
  if (score >= 75) return 'text-phosphor'
  if (score >= 50) return 'text-amber-300'
  return 'text-rose-300'
}

export const formatKyivTime = (iso: string | null): string => kyivStamp(iso)

/** Public Telegram URL for a channel, or null when the ref can't map to one
 * (a numeric tg<id> fallback has no public link). */
export const telegramUrl = (source: Pick<Source, 'subscribe_ref' | 'channel_key'>): string | null => {
  const ref = (source.subscribe_ref ?? source.channel_key ?? '').trim()
  if (!ref) return null
  if (ref.startsWith('http')) return ref
  if (ref.includes('t.me/')) return `https://${ref.replace(/^\/+/, '')}`
  if (ref.startsWith('+')) return `https://t.me/${ref}`
  if (/^tg-?\d+$/i.test(ref) || /^-?\d+$/.test(ref)) return null // numeric id — not linkable
  return `https://t.me/${ref.replace(/^@/, '')}`
}

// Score-component weights — MIRRORS backend app/api/source_stats.py (_W_*).
// Keep in sync; the tooltip renormalizes over whichever components are present,
// exactly like the backend, so the shown total equals stats.quality_score.
const SCORE_WEIGHTS = { coverage: 0.35, correction: 0.35, conflict: 0.15, llm: 0.15 }

export interface ScorePart {
  label: string
  goodness: number // 0..1
  weightPct: number // normalized weight, %
  points: number // contribution to the 0..100 score
}

/** The per-component breakdown behind quality_score, for the hover tooltip. */
export function scoreBreakdown(st: SourceStats): ScorePart[] {
  const raw = [
    { label: 'Покриття', g: st.coverage_rate, w: SCORE_WEIGHTS.coverage },
    { label: 'Без помилок', g: st.correction_rate == null ? null : 1 - st.correction_rate, w: SCORE_WEIGHTS.correction },
    { label: 'Без конфліктів', g: st.conflict_share == null ? null : 1 - st.conflict_share, w: SCORE_WEIGHTS.conflict },
    { label: 'Мало LLM', g: st.llm_fallback_rate == null ? null : 1 - st.llm_fallback_rate, w: SCORE_WEIGHTS.llm },
  ].filter((c): c is { label: string; g: number; w: number } => c.g != null)
  const totalW = raw.reduce((a, c) => a + c.w, 0)
  if (!totalW) return []
  return raw.map((c) => ({
    label: c.label,
    goodness: c.g,
    weightPct: (c.w / totalW) * 100,
    points: (c.w / totalW) * c.g * 100,
  }))
}
