import { Check, Loader2, Microscope } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { analysisKindFor } from '@/lib/cards'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

/** The gamification action in the inspect badge: "Аналіз" for a live target,
 * "Аналіз рештків" for a destroyed one. Only rendered when the setting is on and
 * the user is signed in (cards need an account). Fetches the target's global
 * claim state on show so a slot already taken by someone else reads as disabled. */
export default function AnalyzeButton({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const authed = useRadar((s) => s.authStatus === 'authed')
  const state = useRadar((s) => s.threatStates[threat.id])
  const analyzing = useRadar((s) => s.analyzing)
  const ensureThreatState = useRadar((s) => s.ensureThreatState)
  const analyze = useRadar((s) => s.analyze)

  const kind = analysisKindFor(threat)

  // Load who (if anyone) has already claimed this target's analyses — the twin
  // of inspectThreat fetching events: synced to whichever target is inspected.
  useEffect(() => {
    if (authed && kind) void ensureThreatState(threat.id).catch(() => {})
  }, [authed, kind, threat.id, ensureThreatState])

  if (!authed || !kind) return null

  const taken = kind === 'track' ? state?.track_taken : state?.remains_taken
  const mine = kind === 'track' ? state?.mine_track : state?.mine_remains
  const busy = analyzing?.threatId === threat.id
  const label = kind === 'remains' ? t('game.analyzeRemains') : t('game.analyze')

  if (mine != null) {
    return (
      <span className="flex items-center gap-1 rounded-full bg-white/[0.04] px-2 py-1 text-[11px] font-medium text-slate-500">
        <Check size={12} /> {t('game.collected')}
      </span>
    )
  }

  if (taken && !busy) {
    return (
      <span className="rounded-full bg-white/[0.04] px-2 py-1 text-[11px] text-slate-500">
        {t('game.taken')}
      </span>
    )
  }

  return (
    <button
      onClick={() => void analyze(threat.id, kind)}
      disabled={!!analyzing}
      className="flex items-center gap-1 rounded-full border border-phosphor/30 bg-phosphor/10 px-2.5 py-1 text-[11px] font-medium text-phosphor-soft transition-colors duration-200 hover:bg-phosphor/20 disabled:opacity-50"
    >
      {busy ? <Loader2 size={12} className="animate-spin" /> : <Microscope size={12} />}
      {busy ? t('game.analyzing') : label}
    </button>
  )
}
