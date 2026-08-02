import type { StateCreator } from 'zustand'

import { resyncHomePush } from '@/lib/push'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

import { resyncHomeShare } from './friendsSlice'
import type { RadarState } from './types'

export interface Home {
  lat: number
  lon: number
  radiusKm: number
  /** How the location was set — affects whether we auto-recenter the map. */
  origin: 'geo' | 'manual'
}

function loadHome(): Home | null {
  const raw = safeGet(STORAGE_KEYS.home)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Home
  } catch {
    return null
  }
}

export interface HomeSlice {
  home: Home | null
  /** When true, the next map click sets home (otherwise clicks just pan). */
  placingHome: boolean
  setHome: (h: Home | null) => void
  setHomeRadius: (radiusKm: number) => void
  setPlacingHome: (v: boolean) => void
  /** Adopt the account's stored home WITHOUT sending it back (see
   * friendsSlice.loadFriends, which decides whether to call this). */
  hydrateHome: (h: Home) => void
}

/** Persist locally and push to every server copy that cares. Placing a home is
 * the most laborious thing in the app, so the account is the source of truth
 * and localStorage is a cache for the next paint (and the only store an
 * anonymous visitor gets). */
function persistHome(get: () => RadarState, h: Home | null) {
  if (h) safeSet(STORAGE_KEYS.home, JSON.stringify(h))
  else safeRemove(STORAGE_KEYS.home)
  // The push subscription keeps its OWN copy of the zone — the backend assesses
  // danger against that one. No-op when notifications are off.
  if (get().notifyStatus === 'on') void resyncHomePush(h, get().notifyPrefs).catch(() => {})
  // The account copy is saved whether or not the home is shared: sharing is a
  // visibility choice, not a reason to remember where you live.
  if (get().authStatus === 'authed') void resyncHomeShare(h).catch(() => {})
}

export const createHomeSlice: StateCreator<RadarState, [], [], HomeSlice> = (set, get) => ({
  home: loadHome(),
  placingHome: false,

  setHome: (h) => {
    set({ home: h })
    persistHome(get, h)
  },
  setHomeRadius: (radiusKm) => {
    const cur = get().home
    if (!cur) return
    const next = { ...cur, radiusKm }
    set({ home: next })
    persistHome(get, next)
  },
  setPlacingHome: (v) => set({ placingHome: v }),

  hydrateHome: (h) => {
    safeSet(STORAGE_KEYS.home, JSON.stringify(h))
    set({ home: h })
  },
})
