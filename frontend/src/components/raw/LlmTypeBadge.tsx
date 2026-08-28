import { TYPE_COLORS } from '@/theme'
import type { TargetType } from '@/types'

/** Dev-only chip showing what the LLM type classifier said about a sighting no
 * rule tier could type (backend: parsing/type_llm.py).
 *
 * In shadow mode this is the ONLY place the verdict appears — reviewing these
 * against the type the track actually got is the whole point of the mode, so
 * the chip carries all three fields the decision is made from: the type, where
 * the model got it, and how sure it was. It deliberately does NOT re-implement
 * the "was it applied?" threshold: that lives in one place, the backend's
 * llm_type_min_confidence, and a second copy here would quietly drift.
 */

const EVIDENCE_LABEL: Record<string, string> = {
  text: 'у тексті',
  context: 'з контексту',
  none: 'не визначив',
}

const TYPE_LABEL: Record<TargetType, string> = {
  shahed: 'БПЛА',
  jet_drone: 'реактивний',
  fpv: 'FPV',
  missile: 'ракета',
  ballistic: 'балістика',
  unknown: '—',
}

export default function LlmTypeBadge({
  targetType,
  evidence,
  confidence,
}: {
  targetType: TargetType
  evidence: string | null
  confidence: number | null
}) {
  const declined = targetType === 'unknown' || evidence === 'none'
  return (
    <span
      className={`flex items-center gap-1 whitespace-nowrap rounded px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight ${
        declined ? 'bg-white/[0.06] text-slate-500' : 'bg-white/[0.06]'
      }`}
      style={declined ? undefined : { color: TYPE_COLORS[targetType] }}
      title={`LLM-тип: ${EVIDENCE_LABEL[evidence ?? 'none'] ?? evidence}`}
    >
      ⌁{TYPE_LABEL[targetType]}
      {confidence != null && !declined && (
        <span className="tabular-nums text-slate-400">{confidence.toFixed(2)}</span>
      )}
    </span>
  )
}
