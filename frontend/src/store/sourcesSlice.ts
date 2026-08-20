import type { StateCreator } from 'zustand'

import type { SourceLink } from '@/types'

import type { RadarState } from './types'

export interface SourcesSlice {
  /** The channels this radar reads, for the legend's «Джерела» block.
   *
   * Hydrated on boot with everything else rather than lazily on first open (the
   * way the zone polygons are): this is seven short rows, so deferring it buys
   * nothing and would cost the panel a frame of emptiness on the open that
   * matters. */
  sources: SourceLink[]
  setSources: (s: SourceLink[]) => void
}

export const createSourcesSlice: StateCreator<RadarState, [], [], SourcesSlice> = (set) => ({
  sources: [],
  setSources: (sources) => set({ sources }),
})
