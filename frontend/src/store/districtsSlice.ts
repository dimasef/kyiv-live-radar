import type { StateCreator } from 'zustand'

import type { District, DistrictBoundary } from '@/types'

import type { RadarState } from './types'

export interface DistrictsSlice {
  districts: District[]
  boundaries: DistrictBoundary[]
  setDistricts: (d: District[]) => void
  setBoundaries: (b: DistrictBoundary[]) => void
}

export const createDistrictsSlice: StateCreator<RadarState, [], [], DistrictsSlice> = (set) => ({
  districts: [],
  boundaries: [],
  setDistricts: (d) => set({ districts: d }),
  setBoundaries: (b) => set({ boundaries: b }),
})
