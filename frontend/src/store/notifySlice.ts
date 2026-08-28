import type { StateCreator } from 'zustand'

import { fetchPushPrefs } from '@/api'
import { pushSupported, resyncHomePush, subscribeHomePush, unsubscribeHomePush } from '@/lib/push'
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

/** Phase-1 notification preferences (mirrored to the backend subscription):
 * escalation floor, target-type toggles, and the city-wide alert push. */
export interface NotifyPrefs {
  minLevel: 'warning' | 'danger'
  ballistic: boolean
  missile: boolean
  drone: boolean
  citywide: boolean
}

export const DEFAULT_NOTIFY_PREFS: NotifyPrefs = {
  minLevel: 'warning',
  ballistic: true,
  missile: true,
  drone: true,
  citywide: true,
}

function initialNotifyPrefs(): NotifyPrefs {
  try {
    const saved = JSON.parse(safeGet(STORAGE_KEYS.notifyPrefs) ?? '')
    return { ...DEFAULT_NOTIFY_PREFS, ...saved }
  } catch {
    return DEFAULT_NOTIFY_PREFS
  }
}

/** Server wire shape -> UI prefs. The backend keeps an explicit type list; the
 * UI collapses the two drone types into one toggle (see lib/push.ts::wirePrefs,
 * the inverse of this). */
function fromWirePrefs(wire: {
  min_level?: string
  types?: string[]
  citywide?: boolean
}): NotifyPrefs {
  const types = wire.types ?? []
  return {
    minLevel: wire.min_level === 'danger' ? 'danger' : 'warning',
    ballistic: types.includes('ballistic'),
    missile: types.includes('missile'),
    drone: types.includes('shahed') || types.includes('jet_drone'),
    citywide: wire.citywide ?? true,
  }
}

export interface NotifySlice {
  notifyStatus: NotifyStatus
  notifyPrefs: NotifyPrefs
  enableNotify: () => Promise<void>
  disableNotify: () => Promise<void>
  setNotifyPrefs: (patch: Partial<NotifyPrefs>) => void
  /** Adopt the prefs from the account's last subscription — only ever called
   * for a device that has none of its own (see bootstrap). */
  hydrateNotifyPrefs: () => Promise<void>
}

export const createNotifySlice: StateCreator<RadarState, [], [], NotifySlice> = (set, get) => ({
  notifyStatus: initialNotifyStatus(),
  notifyPrefs: initialNotifyPrefs(),

  hydrateNotifyPrefs: async () => {
    // Never overwrite a choice made on THIS device — a saved key means the user
    // already decided here, and the account copy is just the older sibling.
    if (safeGet(STORAGE_KEYS.notifyPrefs)) return
    const { prefs } = await fetchPushPrefs()
    if (!prefs) return
    set({ notifyPrefs: fromWirePrefs(prefs) })
  },

  setNotifyPrefs: (patch) => {
    const next = { ...get().notifyPrefs, ...patch }
    // Never let every type be off — a subscription that can't fire is a trap
    // the user set for themselves; keep at least one type enabled.
    if (!next.ballistic && !next.missile && !next.drone) return
    safeSet(STORAGE_KEYS.notifyPrefs, JSON.stringify(next))
    set({ notifyPrefs: next })
    if (get().notifyStatus === 'on') {
      void resyncHomePush(get().home, next, get().chosenRegion).catch(() => {})
    }
  },

  enableNotify: async () => {
    const home = get().home
    if (!home || get().notifyStatus === 'unsupported') return
    set({ notifyStatus: 'pending' })
    try {
      const permission = await subscribeHomePush(home, get().notifyPrefs, get().chosenRegion)
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
