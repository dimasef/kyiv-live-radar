import type { StateCreator } from 'zustand'

import { dedupeById } from '@/lib/array'
import type { Notice } from '@/types'

import type { RadarState } from './types'

const NOTICE_CAP = 60

export interface NoticesSlice {
  notices: Notice[]
  setNotices: (n: Notice[]) => void
  /** Non-threat notices (all-clear / summary) go straight to the feed
   * timeline — append-only, unlike alerts which mutate in place. */
  upsertNotice: (notice: Notice) => void
}

export const createNoticesSlice: StateCreator<RadarState, [], [], NoticesSlice> = (set) => ({
  notices: [],
  setNotices: (n) => set({ notices: dedupeById(n) }),
  upsertNotice: (notice) =>
    set((s) => ({
      notices: [notice, ...s.notices.filter((n) => n.id !== notice.id)].slice(0, NOTICE_CAP),
    })),
})
