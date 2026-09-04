import type { StateCreator } from 'zustand'

import { canSeeImpacts, fetchImpacts } from '@/api'
import { currentRegion } from '@/lib/regions'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import type { Threat } from '@/types'

import { shownRegions } from './feedRegions'
import type { RadarState } from './types'

/** Impacts do not arrive over the websocket — `broadcast.py` never fans one out,
 * and that is deliberate, so the layer refreshes on its own clock while it is
 * open. Slow on purpose: a strike location is not a moving target, and this is
 * the one place the app asks for restricted data. */
export const IMPACT_REFRESH_MS = 60_000

export interface ImpactsSlice {
  /** Strike locations for the map layer. Empty until the layer is switched on:
   * nothing fetches them in the background, so an account that never opens the
   * layer never asks the server for them at all. */
  impacts: Threat[]
  impactLayerOn: boolean
  toggleImpactLayer: () => void
  /** Re-read the layer. Called on toggle-on, at boot when the remembered switch
   * is on, and on the refresh tick. A failure (403 after a role was revoked,
   * network) empties the layer rather than leaving a stale answer on the map. */
  refreshImpacts: () => void
}

export const createImpactsSlice: StateCreator<RadarState, [], [], ImpactsSlice> = (set, get) => ({
  impacts: [],
  impactLayerOn: safeGet(STORAGE_KEYS.impactLayer) === '1',

  toggleImpactLayer: () => {
    const on = !get().impactLayerOn
    safeSet(STORAGE_KEYS.impactLayer, on ? '1' : '0')
    set({ impactLayerOn: on, ...(on ? {} : { impacts: [] }) })
    if (on) get().refreshImpacts()
  },

  refreshImpacts: () => {
    const s = get()
    // Checked here as well as in the button: the switch is remembered across
    // reloads, so a revoked role would otherwise keep asking on every tick.
    if (!s.impactLayerOn || !canSeeImpacts(s.user?.role)) return
    fetchImpacts(shownRegions(s.feedExtraRegions, currentRegion(s)))
      .then((impacts) => {
        // The layer may have been switched off while this was in flight.
        if (get().impactLayerOn) set({ impacts })
      })
      .catch(() => set({ impacts: [] }))
  },
})
