import { create } from 'zustand'

import { fetchActiveIncidents, fetchThreatEvents } from './api'
import type {
  District,
  DistrictBoundary,
  FeedEntry,
  Incident,
  Notice,
  Threat,
  WSMessage,
} from './types'

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
  incidents: Incident[]
  log: FeedEntry[]
  notices: Notice[]
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
  setIncidents: (i: Incident[]) => void
  refreshIncidents: () => void
  setLog: (log: FeedEntry[]) => void
  setNotices: (n: Notice[]) => void
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

// Incident aggregates are computed server-side; refetch them (coalesced) shortly
// after live threat activity, rather than recomputing from the flat threats map
// (which evicts closed members). One debounced call covers a burst of events.
let _incidentTimer: ReturnType<typeof setTimeout> | null = null

export const useRadar = create<RadarState>((set, get) => ({
  districts: [],
  boundaries: [],
  threats: {},
  incidents: [],
  log: [],
  notices: [],
  connected: false,
  home: loadHome(),
  placingHome: false,
  inspectedThreat: null,

  setDistricts: (d) => set({ districts: d }),
  setBoundaries: (b) => set({ boundaries: b }),
  setPlacingHome: (v) => set({ placingHome: v }),
  setThreats: (t) =>
    set({ threats: Object.fromEntries(t.map((x) => [x.id, x])) }),
  setIncidents: (i) => set({ incidents: i }),
  refreshIncidents: () => {
    if (_incidentTimer) clearTimeout(_incidentTimer)
    _incidentTimer = setTimeout(() => {
      _incidentTimer = null
      fetchActiveIncidents()
        .then((i) => set({ incidents: i }))
        .catch(() => {})
    }, 800)
  },
  setLog: (log) => set({ log }),
  setNotices: (n) => set({ notices: n }),
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
    // Non-threat notices (all-clear / summary) go straight to the feed timeline.
    if (msg.type === 'notice' && msg.notice) {
      const notice = msg.notice
      set((s) => ({
        notices: [notice, ...s.notices.filter((n) => n.id !== notice.id)].slice(0, LOG_CAP),
      }))
      get().refreshIncidents() // an all-clear ends the incident
      return
    }

    const threat = msg.threat
    if (!threat) return

    // Any live threat activity may open/extend/end an incident — refetch the
    // server-computed aggregates (debounced so a burst collapses to one call).
    get().refreshIncidents()

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
      // Let the closed state show briefly, then drop it — but only if it's still
      // the same closed track (don't delete a threat that changed under us).
      // Impacts are closed-on-creation but are confirmed strike locations that
      // must PERSIST on the map, so they're exempt from eviction.
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
