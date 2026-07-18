import type { StateCreator } from 'zustand'

import { resyncHomePush } from '@/lib/push'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

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
}

export const createHomeSlice: StateCreator<RadarState, [], [], HomeSlice> = (set, get) => ({
  home: loadHome(),
  placingHome: false,

  setHome: (h) => {
    if (h) safeSet(STORAGE_KEYS.home, JSON.stringify(h))
    else safeRemove(STORAGE_KEYS.home)
    set({ home: h })
    // Keep the push subscription's server-side home zone in sync (no-op when
    // notifications are off) — the backend assesses danger against ITS copy.
    if (get().notifyStatus === 'on') void resyncHomePush(h).catch(() => {})
  },
  setHomeRadius: (radiusKm) => {
    const cur = get().home
    if (!cur) return
    const next = { ...cur, radiusKm }
    safeSet(STORAGE_KEYS.home, JSON.stringify(next))
    set({ home: next })
    if (get().notifyStatus === 'on') void resyncHomePush(next).catch(() => {})
  },
  setPlacingHome: (v) => set({ placingHome: v }),
})
