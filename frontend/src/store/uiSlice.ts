import type { StateCreator } from 'zustand'

import type { RadarState } from './types'

export interface UiSlice {
  /** Settings drawer open state — opened from the TopBar gear, closed by the
   * drawer's backdrop/X/Esc. App-level UI state, not a persisted preference. */
  settingsOpen: boolean
  setSettingsOpen: (open: boolean) => void
  /** Bug-report form. Lives here because two places open it (the settings
   * drawer and the account menu) while the form itself is mounted once, in the
   * app shell. */
  bugReportOpen: boolean
  setBugReportOpen: (open: boolean) => void
}

export const createUiSlice: StateCreator<RadarState, [], [], UiSlice> = (set) => ({
  settingsOpen: false,
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  bugReportOpen: false,
  setBugReportOpen: (open) => set({ bugReportOpen: open }),
})
