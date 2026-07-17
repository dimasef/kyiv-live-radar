import type { StateCreator } from 'zustand'

import type { RadarState } from './types'

export interface ConnectionSlice {
  /** The browser's own WS link to this backend. */
  connected: boolean
  /** Whether the live Telegram feed itself looks healthy — null when not
   * applicable (Telegram not configured / simulator mode). Distinct from
   * `connected`. */
  feedOk: boolean | null
  /** How many clients are watching right now — WS headcount pushed by the
   * backend on every connect/disconnect. null until the first frame arrives. */
  online: number | null
  /** A resync (forced reconnect + full rehydrate) is in flight — see
   * `resync()` in ws.ts. Distinct from `connected`: a resync can run while
   * still nominally connected (e.g. resume-from-background). */
  resyncing: boolean
  setConnected: (c: boolean) => void
  setFeedOk: (v: boolean | null) => void
  setOnline: (n: number | null) => void
  setResyncing: (r: boolean) => void
}

export const createConnectionSlice: StateCreator<RadarState, [], [], ConnectionSlice> = (
  set,
) => ({
  connected: false,
  feedOk: null,
  online: null,
  resyncing: false,
  setConnected: (c) => set({ connected: c }),
  setFeedOk: (v) => set({ feedOk: v }),
  setOnline: (n) => set({ online: n }),
  setResyncing: (r) => set({ resyncing: r }),
})
