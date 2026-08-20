import type { AnalysisKind, ThreatAnalysisState } from '@/api'
import { analysisKindFor, isAnalysableTarget, isStale } from '@/lib/cards'
import type { Threat } from '@/types'

/** Whether AnalyzeButton renders anything at all for this target.
 *
 * Exported because its container has to know BEFORE it draws the separator
 * above it. A signed-out viewer, or a target that was never analysable (a
 * city-wide scope, an unlocated «Невідомо»), left a hairline rule floating at
 * the bottom of the popup with nothing underneath it.
 *
 * The button asks this too, so the rule that decides "is there anything here"
 * is written once — a second copy in the popup would be free to drift. */
export function showsAnalyzeAffordance(threat: Threat, authed: boolean): boolean {
  if (!authed) return false
  return analysisKindFor(threat) != null || (isAnalysableTarget(threat) && isStale(threat))
}

export type AnalyzeButtonState =
  /** Claim state not known yet — show an inert placeholder, not an action. */
  | 'checking'
  /** Running right now (this target's analysis). */
  | 'busy'
  /** This user already won this slot. */
  | 'collected'
  /** Someone else won it. */
  | 'taken'
  /** Free to analyse. */
  | 'available'

export function analyzeButtonState({
  kind,
  state,
  failed,
  busy,
}: {
  kind: AnalysisKind
  state: ThreatAnalysisState | undefined
  failed: boolean
  busy: boolean
}): AnalyzeButtonState {
  if (busy) return 'busy'
  if (!state) return failed ? 'available' : 'checking'
  const mine = kind === 'track' ? state.mine_track : state.mine_remains
  if (mine != null) return 'collected'
  const taken = kind === 'track' ? state.track_taken : state.remains_taken
  return taken ? 'taken' : 'available'
}
