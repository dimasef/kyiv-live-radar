import { create } from 'zustand'

import { fetchThreatEvents } from './api'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from './lib/storage'
import type {
  Alert,
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

function loadHome(): Home | null {
  const raw = safeGet(STORAGE_KEYS.home)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Home
  } catch {
    return null
  }
}

interface RadarState {
  districts: District[]
  boundaries: DistrictBoundary[]
  threats: Record<number, Threat>
  incidents: Incident[]
  alerts: Alert[]
  log: FeedEntry[]
  notices: Notice[]
  connected: boolean
  /** Whether the live Telegram feed itself looks healthy — null when not
   * applicable (Telegram not configured / simulator mode). Distinct from
   * `connected` (the browser's own WS link to this backend). */
  feedOk: boolean | null
  home: Home | null
  /** When true, the next map click sets home (otherwise clicks just pan). */
  placingHome: boolean
  /** Track a user picked from the feed to inspect on the map — independent of
   * `threats` (the live layer), so a closed/destroyed track stays visible for
   * as long as the user wants, instead of being evicted after a few seconds. */
  inspectedThreat: Threat | null
  /** The deferred PWA install prompt (captured from `beforeinstallprompt`) —
   * lets InstallControl trigger the native install sheet on demand. Not
   * persisted: the event is non-serializable and only valid for this session. */
  installPrompt: BeforeInstallPromptEvent | null

  setDistricts: (d: District[]) => void
  setBoundaries: (b: DistrictBoundary[]) => void
  setThreats: (t: Threat[]) => void
  setIncidents: (i: Incident[]) => void
  setAlerts: (a: Alert[]) => void
  setLog: (log: FeedEntry[]) => void
  setNotices: (n: Notice[]) => void
  setConnected: (c: boolean) => void
  setFeedOk: (v: boolean | null) => void
  setHome: (h: Home | null) => void
  setHomeRadius: (radiusKm: number) => void
  setPlacingHome: (v: boolean) => void
  setInstallPrompt: (e: BeforeInstallPromptEvent | null) => void
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
  incidents: [],
  alerts: [],
  log: [],
  notices: [],
  connected: false,
  feedOk: null,
  home: loadHome(),
  placingHome: false,
  inspectedThreat: null,
  installPrompt: null,

  setDistricts: (d) => set({ districts: d }),
  setBoundaries: (b) => set({ boundaries: b }),
  setPlacingHome: (v) => set({ placingHome: v }),
  setInstallPrompt: (e) => set({ installPrompt: e }),
  setThreats: (t) =>
    set({ threats: Object.fromEntries(t.map((x) => [x.id, x])) }),
  setIncidents: (i) => set({ incidents: i }),
  setAlerts: (a) => set({ alerts: a }),
  setLog: (log) => set({ log }),
  setNotices: (n) => set({ notices: n }),
  setConnected: (c) => set({ connected: c }),
  setFeedOk: (v) => set({ feedOk: v }),

  setHome: (h) => {
    if (h) safeSet(STORAGE_KEYS.home, JSON.stringify(h))
    else safeRemove(STORAGE_KEYS.home)
    set({ home: h })
  },
  setHomeRadius: (radiusKm) => {
    const cur = get().home
    if (!cur) return
    const next = { ...cur, radiusKm }
    safeSet(STORAGE_KEYS.home, JSON.stringify(next))
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
    // Live feed health (dead Telethon session etc.) — pushed only on change.
    if (msg.type === 'health') {
      set({ feedOk: msg.feed_ok ?? null })
      return
    }

    // Official alert windows (тривога/відбій) — replace by id since, unlike
    // notices (append-only), the SAME alert mutates in place (start -> end).
    if (msg.type === 'alert' && msg.alert) {
      const alert = msg.alert
      set((s) => ({ alerts: [alert, ...s.alerts.filter((a) => a.id !== alert.id)] }))
      return
    }

    // Attack (incident) state pushed straight from the server on every
    // change — replaces the old debounced refetch-on-any-threat-event
    // pattern. Ended incidents drop out of the (implicitly "active") list.
    if (msg.type === 'attack' && msg.incident) {
      const incident = msg.incident
      set((s) => ({
        incidents:
          incident.status === 'ended'
            ? s.incidents.filter((i) => i.id !== incident.id)
            : [incident, ...s.incidents.filter((i) => i.id !== incident.id)],
      }))
      return
    }

    // Non-threat notices (all-clear / summary) go straight to the feed timeline.
    if (msg.type === 'notice' && msg.notice) {
      const notice = msg.notice
      set((s) => ({
        notices: [notice, ...s.notices.filter((n) => n.id !== notice.id)].slice(0, LOG_CAP),
      }))
      return
    }

    const threat = msg.threat
    if (!threat) return

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
