import type { StateCreator } from 'zustand'

import type { RadarState } from './types'

export interface PwaSlice {
  /** The deferred PWA install prompt (captured from `beforeinstallprompt`) —
   * lets InstallControl trigger the native install sheet on demand. Not
   * persisted: the event is non-serializable and only valid for this session. */
  installPrompt: BeforeInstallPromptEvent | null
  setInstallPrompt: (e: BeforeInstallPromptEvent | null) => void
}

export const createPwaSlice: StateCreator<RadarState, [], [], PwaSlice> = (set) => ({
  installPrompt: null,
  setInstallPrompt: (e) => set({ installPrompt: e }),
})
