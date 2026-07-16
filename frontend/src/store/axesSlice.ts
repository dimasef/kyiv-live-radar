import type { StateCreator } from 'zustand'

import type { ThreatAxis } from '@/types'

import type { RadarState } from './types'

export interface AxesSlice {
  axes: ThreatAxis[]
  setAxes: (a: ThreatAxis[]) => void
  /** Directional axes pushed from the server. An expired axis drops out of the
   * (implicitly "live") list; otherwise replaces by id. */
  upsertAxis: (axis: ThreatAxis) => void
}

export const createAxesSlice: StateCreator<RadarState, [], [], AxesSlice> = (set) => ({
  axes: [],
  setAxes: (a) => set({ axes: a }),
  upsertAxis: (axis) =>
    set((s) => ({
      axes:
        axis.status === 'expired'
          ? s.axes.filter((a) => a.id !== axis.id)
          : [axis, ...s.axes.filter((a) => a.id !== axis.id)],
    })),
})
