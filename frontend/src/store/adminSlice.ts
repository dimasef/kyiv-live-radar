import type { StateCreator } from 'zustand'

import { fetchAdminThreat, regroupEvent } from '@/api'
import type { Threat } from '@/types'

import type { RadarState } from './types'

/** Which sighting is looking for a new home, and where it currently lives. */
export interface RegroupPick {
  eventId: number
  sourceThreatId: number
}

export interface AdminSlice {
  /** The track opened in the on-map editor. Loaded through the ADMIN route, so
   * closed tracks open too — the public one withholds them. */
  adminTrack: Threat | null
  openAdminTrack: (id: number) => void
  applyAdminTrack: (track: Threat) => void
  closeAdminTrack: () => void
  /** Regrouping a sighting by picking its new track off the map, because on the
   * map the T-numbers the «Весь фід» editor asks to be typed are nowhere to be
   * seen. Non-null puts every other target marker into pick mode. */
  regroupPick: RegroupPick | null
  startRegroupPick: (pick: RegroupPick) => void
  cancelRegroupPick: () => void
  completeRegroupPick: (targetThreatId: number) => Promise<void>
}

export const createAdminSlice: StateCreator<RadarState, [], [], AdminSlice> = (set, get) => ({
  adminTrack: null,

  openAdminTrack: (id) => {
    fetchAdminThreat(id)
      .then((track) => set({ adminTrack: track }))
      .catch(() => {})
  },
  applyAdminTrack: (track) =>
    // Only if the editor is still on THIS track: an action's response can land
    // after the operator has closed the dialog or opened another one.
    set((s) => (s.adminTrack?.id === track.id ? { adminTrack: track } : {})),
  closeAdminTrack: () => set({ adminTrack: null, regroupPick: null }),

  regroupPick: null,
  startRegroupPick: (pick) => set({ regroupPick: pick }),
  cancelRegroupPick: () => set({ regroupPick: null }),

  completeRegroupPick: async (targetThreatId) => {
    const pick = get().regroupPick
    if (!pick || targetThreatId === pick.sourceThreatId) return
    const result = await regroupEvent(pick.eventId, targetThreatId)
    // A regroup always answers with BOTH tracks, and the editor stays on
    // whichever of them still owns the sightings it was showing — after a move
    // onto another track that is the source, minus the one that left (the same
    // rule TrackEditModal applies to its own moves).
    const open = get().adminTrack
    set({
      regroupPick: null,
      adminTrack:
        open == null
          ? null
          : result.source_threat.id === open.id
            ? result.source_threat
            : result.threat,
    })
    // The map and the feed need no help here — the server broadcasts both
    // tracks over the websocket.
  },
})
