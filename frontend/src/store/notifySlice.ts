import type { StateCreator } from 'zustand'

import { pushSupported, subscribeHomePush, unsubscribeHomePush } from '@/lib/push'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

import type { RadarState } from './types'

/** Danger-near-home push opt-in state. 'on' is persisted so boot can resync a
 * still-live browser subscription (see bootstrap.ts); the browser permission is
 * re-checked at init — a permission revoked from browser settings degrades the
 * saved 'on' back to 'off'/'denied' instead of pretending. */
export type NotifyStatus = 'unsupported' | 'off' | 'pending' | 'on' | 'denied'

function initialNotifyStatus(): NotifyStatus {
  if (!pushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  const optedIn = safeGet(STORAGE_KEYS.notify) === '1'
  return optedIn && Notification.permission === 'granted' ? 'on' : 'off'
}

export interface NotifySlice {
  notifyStatus: NotifyStatus
  enableNotify: () => Promise<void>
  disableNotify: () => Promise<void>
}

export const createNotifySlice: StateCreator<RadarState, [], [], NotifySlice> = (set, get) => ({
  notifyStatus: initialNotifyStatus(),

  enableNotify: async () => {
    const home = get().home
    if (!home || get().notifyStatus === 'unsupported') return
    set({ notifyStatus: 'pending' })
    try {
      const permission = await subscribeHomePush(home)
      if (permission === 'granted') {
        safeSet(STORAGE_KEYS.notify, '1')
        set({ notifyStatus: 'on' })
      } else {
        set({ notifyStatus: permission === 'denied' ? 'denied' : 'off' })
      }
    } catch {
      set({ notifyStatus: 'off' })
    }
  },

  disableNotify: async () => {
    safeRemove(STORAGE_KEYS.notify)
    set({ notifyStatus: 'off' })
    try {
      await unsubscribeHomePush()
    } catch {
      // The server row (if any) dies on its next 410 push anyway.
    }
  },
})
