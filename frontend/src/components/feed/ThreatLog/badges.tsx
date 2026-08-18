import type { ReactNode } from 'react'

import { kyivClock } from '@/lib/kyivTime'

export function EventTime({ iso }: { iso: string }) {
  return (
    <span className="font-mono text-[10px] tabular-nums text-slate-500">{kyivClock(iso)}</span>
  )
}

// Dev-only ID badge — lets the maintainer paste "T207/M646" straight into a
// Claude Code chat instead of describing a message, so Claude can jump
// straight to `threats`/`threat_events` rows instead of re-deriving them from
// district/time/text. import.meta.env.DEV is Vite's native flag: true under
// `npm run dev`, stripped out of the prod build (`npm run build`), so this
// never ships to Vercel.
export function DevId({ children }: { children: ReactNode }) {
  if (!import.meta.env.DEV) return null
  return (
    <span className="rounded bg-white/[0.06] px-1 py-0.5 font-mono text-[9px] tracking-tight text-slate-500">
      {children}
    </span>
  )
}

// Dev-only: flags events resolved by the LLM fallback (app/parsing/llm.py,
// ~5% of rule-misses) — silent for the rule-parser majority so it doesn't
// add noise to every single card.
export function DevSource({ source }: { source: string }) {
  if (!import.meta.env.DEV || source !== 'llm') return null
  return (
    <span className="rounded bg-violet-400/15 px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight text-violet-300">
      LLM
    </span>
  )
}
