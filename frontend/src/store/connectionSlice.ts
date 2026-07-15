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
  setConnected: (c: boolean) => void
  setFeedOk: (v: boolean | null) => void
  setOnline: (n: number | null) => void
}

export const createConnectionSlice: StateCreator<RadarState, [], [], ConnectionSlice> = (
  set,
) => ({
  connected: false,
  feedOk: null,
  online: null,
  setConnected: (c) => set({ connected: c }),
  setFeedOk: (v) => set({ feedOk: v }),
  setOnline: (n) => set({ online: n }),
})
