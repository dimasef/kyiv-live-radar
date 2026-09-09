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
 * clock — whether or not it is open, because the button's badge has to say
 * what is under it before it is pressed. Slow on purpose: neither a strike
 * location nor a burnt-out building moves, and this is the one place the app
 * asks for restricted data. */
export const IMPACT_REFRESH_MS = 60_000

export interface ImpactsSlice {
  /** Strike locations for the map layer. Fetched on the refresh tick for every
   * account allowed to see them, open or not, so the button can carry a count;
   * an account without the role never asks. */
  impacts: Threat[]
  /** The same layer's other half: what a strike DID to a raion. One toggle
   * covers both — the reader is asking one question ("what did this night do to
   * these streets") and the two answers differ only in whether anyone confirmed
   * the hit itself. */
  aftermath: Aftermath[]
  impactLayerOn: boolean
  /** Set for IMPACT_NOTICE_MS after a toggle so the top-centre stack can say
   * what just happened (banners/ImpactLayerNotice) — the same rule as the
   * raion-alert layer: only a gesture announces, a remembered switch does not.
   *
   * 'error' is the exception to that rule: it is raised by a failed request,
   * not by a gesture, and it STAYS until the next successful refresh. An empty
   * layer used to mean both "nothing happened tonight" and "the request died",
   * which is exactly how a route that 500'd on every real impact went five
   * releases unnoticed (see api/public/threats.py::live_impacts). */
  impactLayerNotice: 'on' | 'off' | 'error' | null
  toggleImpactLayer: () => void
  /** Re-read BOTH halves. Called on toggle-on and on the refresh tick, which
   * runs as long as the role allows it. A failure (403 after a role was
   * revoked, network) empties that half rather than leaving a stale answer on
   * the map — each request clears only its own, so one endpoint failing does
   * not blank the other. The error pill is only raised while the layer is
   * open: with it off there is no map to be missing anything from. */
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
    set({ impactLayerOn: on, impactLayerNotice: on ? 'on' : 'off' })
    clearTimeout(noticeTimer)
    // Only the gesture's own notice is timed out. An 'error' raised by the
    // refresh this toggle kicks off must not be wiped by this timer, so it
    // clears the pill only while it is still showing what the gesture said.
    noticeTimer = setTimeout(() => {
      if (get().impactLayerNotice !== 'error') set({ impactLayerNotice: null })
    }, IMPACT_NOTICE_MS)
    if (on) get().refreshImpacts()
  },

  refreshImpacts: () => {
    const s = get()
    // Checked here as well as in the layer: a revoked role must stop the tick.
    if (!canSeeImpacts(s.user?.role)) return
    const regions = shownRegions(s.feedExtraRegions, currentRegion(s))
    const fail = (half: 'impacts' | 'aftermath') => () =>
      set({ [half]: [], ...(get().impactLayerOn ? { impactLayerNotice: 'error' } : {}) })
    fetchImpacts(regions)
      .then((impacts) => {
        // Clearing the error here rather than before the request: a failing
        // half must keep saying so while the other half succeeds.
        set({ impacts })
        if (get().impactLayerNotice === 'error') set({ impactLayerNotice: null })
      })
      .catch(fail('impacts'))
    fetchAftermath(regions)
      .then((aftermath) => set({ aftermath }))
      .catch(fail('aftermath'))
  },
})
