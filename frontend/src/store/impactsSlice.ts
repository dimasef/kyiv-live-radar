import type { StateCreator } from 'zustand'

import { canSeeImpacts, fetchAftermath, fetchImpacts } from '@/api'
import { currentRegion } from '@/lib/regions'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import type { Aftermath, Threat } from '@/types'

import { shownRegions } from './feedRegions'
import type { RadarState } from './types'

/** Neither half of this layer arrives over the websocket — `broadcast.py` never
 * fans out an impact and there is no message type for a report at all. That is
 * deliberate (the absence of a broadcast is the cheapest guarantee the data
 * can't reach a frame everyone receives), so the layer refreshes on its own
 * clock while it is open. Slow on purpose: neither a strike location nor a
 * burnt-out building moves, and this is the one place the app asks for
 * restricted data. */
export const IMPACT_REFRESH_MS = 60_000

export interface ImpactsSlice {
  /** Strike locations for the map layer. Empty until the layer is switched on:
   * nothing fetches them in the background, so an account that never opens the
   * layer never asks the server for them at all. */
  impacts: Threat[]
  /** The same layer's other half: what a strike DID to a raion. One toggle
   * covers both — the reader is asking one question ("what did this night do to
   * these streets") and the two answers differ only in whether anyone confirmed
   * the hit itself. */
  aftermath: Aftermath[]
  impactLayerOn: boolean
  /** Set for IMPACT_NOTICE_MS after a toggle so the top-centre stack can say
   * what just happened (banners/ImpactLayerNotice) — the same rule as the
   * raion-alert layer: only a gesture announces, a remembered switch does not. */
  impactLayerNotice: 'on' | 'off' | null
  toggleImpactLayer: () => void
  /** Re-read BOTH halves. Called on toggle-on, at boot when the remembered
   * switch is on, and on the refresh tick. A failure (403 after a role was
   * revoked, network) empties that half rather than leaving a stale answer on
   * the map — each request clears only its own, so one endpoint failing does
   * not blank the other. */
  refreshImpacts: () => void
}

export const IMPACT_NOTICE_MS = 5000
let noticeTimer: ReturnType<typeof setTimeout> | undefined

export const createImpactsSlice: StateCreator<RadarState, [], [], ImpactsSlice> = (set, get) => ({
  impacts: [],
  aftermath: [],
  impactLayerOn: safeGet(STORAGE_KEYS.impactLayer) === '1',
  impactLayerNotice: null,

  toggleImpactLayer: () => {
    const on = !get().impactLayerOn
    safeSet(STORAGE_KEYS.impactLayer, on ? '1' : '0')
    set({
      impactLayerOn: on,
      impactLayerNotice: on ? 'on' : 'off',
      ...(on ? {} : { impacts: [], aftermath: [] }),
    })
    clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => set({ impactLayerNotice: null }), IMPACT_NOTICE_MS)
    if (on) get().refreshImpacts()
  },

  refreshImpacts: () => {
    const s = get()
    // Checked here as well as in the button: the switch is remembered across
    // reloads, so a revoked role would otherwise keep asking on every tick.
    if (!s.impactLayerOn || !canSeeImpacts(s.user?.role)) return
    const regions = shownRegions(s.feedExtraRegions, currentRegion(s))
    fetchImpacts(regions)
      .then((impacts) => {
        // The layer may have been switched off while this was in flight.
        if (get().impactLayerOn) set({ impacts })
      })
      .catch(() => set({ impacts: [] }))
    fetchAftermath(regions)
      .then((aftermath) => {
        if (get().impactLayerOn) set({ aftermath })
      })
      .catch(() => set({ aftermath: [] }))
  },
})
