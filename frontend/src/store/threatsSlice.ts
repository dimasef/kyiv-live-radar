import type { StateCreator } from 'zustand'

import { fetchThreatEvents } from '@/api'
import type { FeedEntry, Threat, ThreatEvent } from '@/types'

import type { RadarState } from './types'

const LOG_CAP = 60
// How long a closed (destroyed/lost) track lingers on the map before it clears.
const CLOSED_LINGER_MS = 6000

export interface ThreatsSlice {
  threats: Record<number, Threat>
  log: FeedEntry[]
  /** Track a user picked from the feed to inspect on the map — independent of
   * `threats` (the live layer), so a closed/destroyed track stays visible for
   * as long as the user wants, instead of being evicted after a few seconds. */
  inspectedThreat: Threat | null
  setThreats: (t: Threat[]) => void
  setLog: (log: FeedEntry[]) => void
  inspectThreat: (threat: Threat) => void
  clearInspection: () => void
  /** Apply one live threat-bearing WS message: upsert the track, append its
   * feed entry (for 'event' frames), and schedule eviction once closed. */
  applyThreatMessage: (msg: { type: string; threat: Threat; event?: ThreatEvent }) => void
}

export const createThreatsSlice: StateCreator<RadarState, [], [], ThreatsSlice> = (set, get) => ({
  threats: {},
  log: [],
  inspectedThreat: null,

  setThreats: (t) => set({ threats: Object.fromEntries(t.map((x) => [x.id, x])) }),

  setLog: (log) => {
    const seen = new Set<number>()
    set({
      log: log.filter((e) => (seen.has(e.event.id) ? false : (seen.add(e.event.id), true))),
    })
  },

  inspectThreat: (threat) => {
    // Show what we already have (from the feed entry) immediately, then fill
    // in the full event history — works even if the track is closed/evicted
    // from `threats`, since this doesn't read from it at all.
    set({ inspectedThreat: threat })
    fetchThreatEvents(threat.id)
      .then((events) => {
        // Guard against a stale response landing after the user picked a
        // different (or no) track in the meantime.
        if (get().inspectedThreat?.id === threat.id) {
          set({ inspectedThreat: { ...threat, events } })
        }
      })
      .catch(() => {})
  },
  clearInspection: () => set({ inspectedThreat: null }),

  applyThreatMessage: (msg) => {
    const { threat } = msg

    // Never resurrect a track already closed on the map (guards against stale
    // out-of-order events re-adding a threat that was cleared).
    const existing = get().threats[threat.id]
    if (msg.type === 'event' && existing?.closed_at) return

    set((s) => ({ threats: { ...s.threats, [threat.id]: threat } }))

    if (msg.type === 'event' && msg.event) {
      const entry: FeedEntry = { event: msg.event, threat }
      // Drop any existing entry with the same event id first — event ids can
      // get reused after a destructive DB rebuild (e.g. scripts/
      // reprocess_raw.py on SQLite dev, which restarts the id sequence from
      // 1), which would otherwise leave two React list items with the same
      // key (a real warning seen live) until the next full page reload.
      set((s) => ({
        log: [entry, ...s.log.filter((e) => e.event.id !== entry.event.id)].slice(0, LOG_CAP),
      }))
    }

    if (threat.closed_at && threat.status !== 'impact') {
      // Let the closed state show briefly, then drop it — but only if it's
      // still the same closed track (don't delete a threat that changed
      // under us). Impacts are closed-on-creation but are confirmed strike
      // locations that must PERSIST on the map, so they're exempt.
      const closedAt = threat.closed_at
      setTimeout(() => {
        const cur = get().threats[threat.id]
        if (cur && cur.closed_at === closedAt) {
          const next = { ...get().threats }
          delete next[threat.id]
          set({ threats: next })
        }
      }, CLOSED_LINGER_MS)
    }
  },
})
