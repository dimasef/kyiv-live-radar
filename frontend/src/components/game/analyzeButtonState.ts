import type { AnalysisKind, ThreatAnalysisState } from '@/api'

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
