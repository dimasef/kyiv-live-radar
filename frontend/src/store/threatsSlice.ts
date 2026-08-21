import type { StateCreator } from 'zustand'

import { fetchThreatEvents } from '@/api'
import type { FeedEntry, Threat, ThreatEvent } from '@/types'

import type { RadarState } from './types'

// How long a closed (destroyed/lost) track lingers on the map before it clears.
const CLOSED_LINGER_MS = 6000
// The tail of that linger spent fading out, so a track never blinks out of
// existence — most visible on «Чисто», which closes dozens at once. The store
// owns this timeline (not a 6s CSS animation) precisely so the fade can be HELD
// BACK: a track the user is reading must not dissolve under them.
const LEAVE_MS = 700

// One exit timeline per track. A closed track can arrive on several frames (a
// retype right after the close, a corroborating source), and without this each
// one starts its own chain: the id gets pushed into `leavingThreatIds` twice,
// then the first chain's cleanup filters out BOTH entries and kills the second
// chain's fade mid-animation while its eviction timer is still pending.
const exitTimers = new Map<number, ReturnType<typeof setTimeout>>()

function scheduleExit(threatId: number, run: () => void, delayMs: number) {
  const pending = exitTimers.get(threatId)
  if (pending) clearTimeout(pending)
  exitTimers.set(
    threatId,
    setTimeout(() => {
      exitTimers.delete(threatId)
      run()
    }, delayMs),
  )
}

export interface ThreatsSlice {
  threats: Record<number, Threat>
  log: FeedEntry[]
  /** Track a user picked from the feed to inspect on the map — independent of
   * `threats` (the live layer), so a closed/destroyed track stays visible for
   * as long as the user wants, instead of being evicted after a few seconds. */
  inspectedThreat: Threat | null
  /** Closed tracks currently playing their exit fade — the last LEAVE_MS before
   * eviction. Held back while the user is reading one (popup open / inspected). */
  leavingThreatIds: number[]
  /** Which track has its map popup open, if any — a marker being read is never
   * evicted from under the reader. */
  openPopupThreatId: number | null
  setOpenPopupThreat: (id: number | null) => void
  setThreats: (t: Threat[]) => void
  setLog: (log: FeedEntry[]) => void
  inspectThreat: (threat: Threat) => void
  clearInspection: () => void
  /** Apply one live threat-bearing WS message: upsert the track, append its
   * feed entry (for 'event' frames), and schedule eviction once closed. */
  applyThreatMessage: (msg: {
    type: 'event' | 'status'
    threat: Threat
    event?: ThreatEvent
  }) => void
}

export const createThreatsSlice: StateCreator<RadarState, [], [], ThreatsSlice> = (set, get) => ({
  threats: {},
  log: [],
  inspectedThreat: null,
  leavingThreatIds: [],
  openPopupThreatId: null,

  setOpenPopupThreat: (id) => set({ openPopupThreatId: id }),

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
        // different (or no) track in the meantime. Merged onto the CURRENT copy,
        // not the one captured when the fetch started — a status frame (an admin
        // retype, a «збито») may have landed while it was in flight, and
        // spreading the old snapshot would silently undo it.
        set((s) =>
          s.inspectedThreat?.id === threat.id
            ? { inspectedThreat: { ...s.inspectedThreat, events } }
            : {},
        )
      })
      .catch(() => {})
  },
  clearInspection: () => set({ inspectedThreat: null }),

  applyThreatMessage: (msg) => {
    const { threat } = msg

    // An EVENT frame never (re-)opens a closed track on the map: it's already
    // gone, or already playing its exit, and re-adding it makes the dot flash
    // back for the whole linger. Such frames are normal — an out-of-order
    // sighting, or a «збито» that lands after the sweeper retired the target
    // (the backend relabels that close and broadcasts the news as an event).
    // Only the map write is skipped, never the frame: the feed and the inspected
    // copy are exactly where that news belongs. Impacts are closed on creation
    // but are permanent map pins, and a track still on screen keeps taking
    // updates so its exit shows the corrected status.
    const onMap = get().threats[threat.id] != null
    const showOnMap =
      msg.type !== 'event' || !threat.closed_at || threat.status === 'impact' || onMap

    // The feed's cards and the inspected copy each embed their OWN snapshot of
    // the track, taken when the event arrived — so a later change to it (an
    // admin retype, a «збито») reached the map instantly while the feed kept
    // showing the old type until a reload. Every threat-bearing frame refreshes
    // all three copies together.
    set((s) => ({
      threats: showOnMap ? { ...s.threats, [threat.id]: threat } : s.threats,
      log: s.log.map((e) => (e.threat.id === threat.id ? { ...e, threat } : e)),
      inspectedThreat:
        s.inspectedThreat?.id === threat.id
          ? // Keep the inspected event history: inspectThreat fetches the FULL
            // list, which a broadcast doesn't have to carry.
            { ...threat, events: threat.events.length ? threat.events : s.inspectedThreat.events }
          : s.inspectedThreat,
    }))

    if (msg.type === 'event' && msg.event) {
      const entry: FeedEntry = { event: msg.event, threat }
      // Drop any existing entry with the same event id first — event ids can
      // get reused after a destructive DB rebuild (e.g. scripts/
      // reprocess_raw.py on SQLite dev, which restarts the id sequence from
      // 1), which would otherwise leave two React list items with the same
      // key (a real warning seen live) until the next full page reload.
      set((s) => ({
        log: [entry, ...s.log.filter((e) => e.event.id !== entry.event.id)].slice(0, s.feedLimit),
      }))
    }

    if (threat.status === 'dismissed') {
      // Admin manually cancelled a false positive — remove it from the map
      // immediately (no linger; it shouldn't have been there at all), and from
      // the feed with it: /events/recent hides a dismissed track's events, so
      // leaving the cards would only differ from what the next reload shows.
      set((s) => {
        const next = { ...s.threats }
        delete next[threat.id]
        return { threats: next, log: s.log.filter((e) => e.threat.id !== threat.id) }
      })
      return
    }

    if (threat.closed_at && threat.status !== 'impact') {
      // Let the closed state show briefly, fade it, then drop it — but only if
      // it's still the same closed track (don't delete a threat that changed
      // under us). Impacts are closed-on-creation but are confirmed strike
      // locations that must PERSIST on the map, so they're exempt.
      const closedAt = threat.closed_at
      const stillTheSame = () => {
        const cur = get().threats[threat.id]
        return cur != null && cur.closed_at === closedAt
      }
      // Someone reading this target's popup, or inspecting it from the feed,
      // has said they want it — postpone the whole exit rather than dissolving
      // it mid-read (the inspected copy is deliberately permanent, see above).
      const held = () =>
        get().openPopupThreatId === threat.id || get().inspectedThreat?.id === threat.id

      const startLeave = () => {
        if (!stillTheSame()) return
        if (held()) {
          scheduleExit(threat.id, startLeave, LEAVE_MS)
          return
        }
        set((s) => ({
          leavingThreatIds: s.leavingThreatIds.includes(threat.id)
            ? s.leavingThreatIds
            : [...s.leavingThreatIds, threat.id],
        }))
        scheduleExit(
          threat.id,
          () => {
            const done = stillTheSame()
            set((s) => ({
              leavingThreatIds: s.leavingThreatIds.filter((id) => id !== threat.id),
              threats: done
                ? Object.fromEntries(
                    Object.entries(s.threats).filter(([id]) => Number(id) !== threat.id),
                  )
                : s.threats,
            }))
          },
          LEAVE_MS,
        )
      }
      scheduleExit(threat.id, startLeave, CLOSED_LINGER_MS - LEAVE_MS)
    }
  },
})
