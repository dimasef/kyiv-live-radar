import type { StateCreator } from 'zustand'

import type { RadarState } from './types'

/** How often the fade clock advances. A 20-minute stale window moves ~1% of
 * opacity per tick, so the steps are imperceptible (and CSS smooths them) while
 * costing one re-render per visible target every 10 s. */
const TICK_MS = 10_000

/** Ignore an absurd server/client difference rather than trusting it — a wildly
 * wrong offset would be worse than none. Half an hour is far more than real
 * clock drift and far less than a misconfigured timezone/date. */
const MAX_SKEW_MS = 30 * 60 * 1000

export interface ClockSlice {
  /** Ticking wall clock for age-dependent rendering. Advances on a timer, so a
   * target's fade progresses without any server traffic. */
  nowMs: number
  /** server − device, from `/health` and every WS 'ping'. Absolute `stale_at`
   * timestamps are meaningless against a device clock that's off by minutes
   * (TV browsers are the usual offender), which would fade every target at once
   * or never. */
  clockSkewMs: number
  /** Server-corrected now — what every freshness calculation should use. */
  serverNow: () => number
  tickClock: () => void
  setServerTime: (iso: string | null | undefined) => void
  startClock: () => void
}

export const createClockSlice: StateCreator<RadarState, [], [], ClockSlice> = (set, get) => ({
  nowMs: Date.now(),
  clockSkewMs: 0,
  serverNow: () => get().nowMs + get().clockSkewMs,
  tickClock: () => set({ nowMs: Date.now() }),
  setServerTime: (iso) => {
    if (!iso) return
    const server = Date.parse(iso)
    if (Number.isNaN(server)) return
    const skew = server - Date.now()
    set({ clockSkewMs: Math.abs(skew) > MAX_SKEW_MS ? 0 : skew })
  },
  startClock: () => {
    // Paused while the tab is hidden: nothing is on screen to fade, and a
    // background timer is pure battery cost. The visibility handler ticks
    // immediately on resume so the map never shows a frozen age.
    let timer: ReturnType<typeof setInterval> | null = null
    const stop = () => {
      if (timer != null) clearInterval(timer)
      timer = null
    }
    const start = () => {
      if (timer == null) timer = setInterval(() => get().tickClock(), TICK_MS)
    }
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        get().tickClock()
        start()
      } else {
        stop()
      }
    })
    if (document.visibilityState === 'visible') start()
  },
})
