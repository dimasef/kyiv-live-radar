import { create } from 'zustand'

import { fetchThreatEvents } from './api'
import type { District, DistrictBoundary, FeedEntry, Threat, WSMessage } from './types'

export interface Home {
  lat: number
  lon: number
  radiusKm: number
  /** How the location was set — affects whether we auto-recenter the map. */
  origin: 'geo' | 'manual'
}

const HOME_KEY = 'klr-home'

function loadHome(): Home | null {
  try {
    const raw = localStorage.getItem(HOME_KEY)
    return raw ? (JSON.parse(raw) as Home) : null
  } catch {
    return null
  }
}

interface RadarState {
  districts: District[]
  boundaries: DistrictBoundary[]
  threats: Record<number, Threat>
  log: FeedEntry[]
  connected: boolean
  home: Home | null
  /** When true, the next map click sets home (otherwise clicks just pan). */
  placingHome: boolean
  /** Track a user picked from the feed to inspect on the map — independent of
   * `threats` (the live layer), so a closed/destroyed track stays visible for
   * as long as the user wants, instead of being evicted after a few seconds. */
  inspectedThreat: Threat | null

  setDistricts: (d: District[]) => void
  setBoundaries: (b: DistrictBoundary[]) => void
  setThreats: (t: Threat[]) => void
  setLog: (log: FeedEntry[]) => void
  setConnected: (c: boolean) => void
  setHome: (h: Home | null) => void
  setHomeRadius: (radiusKm: number) => void
  setPlacingHome: (v: boolean) => void
  inspectThreat: (threat: Threat) => void
  clearInspection: () => void
  handleWS: (msg: WSMessage) => void
}

const LOG_CAP = 60
// How long a closed (destroyed/lost) track lingers on the map before it clears.
const CLOSED_LINGER_MS = 6000

export const useRadar = create<RadarState>((set, get) => ({
  districts: [],
  boundaries: [],
  threats: {},
  log: [],
  connected: false,
  home: loadHome(),
  placingHome: false,
  inspectedThreat: null,

  setDistricts: (d) => set({ districts: d }),
  setBoundaries: (b) => set({ boundaries: b }),
  setPlacingHome: (v) => set({ placingHome: v }),
  setThreats: (t) =>
    set({ threats: Object.fromEntries(t.map((x) => [x.id, x])) }),
  setLog: (log) => set({ log }),
  setConnected: (c) => set({ connected: c }),

  setHome: (h) => {
    if (h) localStorage.setItem(HOME_KEY, JSON.stringify(h))
    else localStorage.removeItem(HOME_KEY)
    set({ home: h })
  },
  setHomeRadius: (radiusKm) => {
    const cur = get().home
    if (!cur) return
    const next = { ...cur, radiusKm }
    localStorage.setItem(HOME_KEY, JSON.stringify(next))
    set({ home: next })
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

  handleWS: (msg) => {
    const threat = msg.threat
    if (!threat) return

    // Never resurrect a track already closed on the map (guards against stale
    // out-of-order events re-adding a threat that was cleared).
    const existing = get().threats[threat.id]
    if (msg.type === 'event' && existing?.closed_at) return

    set((s) => ({ threats: { ...s.threats, [threat.id]: threat } }))

    if (msg.type === 'event' && msg.event) {
      const entry: FeedEntry = { event: msg.event, threat }
      set((s) => ({ log: [entry, ...s.log].slice(0, LOG_CAP) }))
    }

    if (threat.closed_at) {
      // Let the closed state show briefly, then drop it — but only if it's still
      // the same closed track (don't delete a threat that changed under us).
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
}))
