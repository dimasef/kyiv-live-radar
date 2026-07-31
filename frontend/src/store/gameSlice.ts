import type { StateCreator } from 'zustand'

import {
  ApiError,
  fetchCollection,
  fetchThreatAnalysisState,
  postAnalysis,
  type AnalysisKind,
  type Collection,
  type ThreatAnalysisState,
} from '@/api'

import type { RadarState } from './types'

// The "analysing…" animation runs a random time in this window before the card
// drops — the suspense IS the point; keep it passive so the user can put the
// phone down. (Design: 3–10s.)
const ANALYSIS_MIN_MS = 3000
const ANALYSIS_MAX_MS = 10000

function analysisDelayMs(): number {
  return ANALYSIS_MIN_MS + Math.floor(Math.random() * (ANALYSIS_MAX_MS - ANALYSIS_MIN_MS + 1))
}

export interface GameSlice {
  /** The current user's card collection (null until first load / logged out). */
  collection: Collection | null
  /** Per-target global claim state, cached as targets are inspected. */
  threatStates: Record<number, ThreatAnalysisState>
  /** The analysis currently running (drives the scanning overlay), or null. */
  analyzing: { threatId: number; kind: AnalysisKind } | null
  /** A freshly-won card to show in the reveal modal, or null. `isNew` is false
   * when the user already owned a copy (a duplicate); `count` is the resulting
   * total copies, so the reveal can badge and caption it accordingly. */
  reveal: { cardId: number; kind: AnalysisKind; isNew: boolean; count: number } | null
  /** Why the last claim failed: 'taken' (someone won it first) or 'error'. */
  claimError: 'taken' | 'error' | null

  loadCollection: () => Promise<void>
  clearGame: () => void
  /** Load a target's claim state into the cache if not already there. */
  ensureThreatState: (threatId: number) => Promise<void>
  /** Run an analysis: the 3–10s wait, then claim a card (or surface a 409). */
  analyze: (threatId: number, kind: AnalysisKind) => Promise<void>
  /** Dismiss the reveal / error modal. */
  dismissReveal: () => void
}

export const createGameSlice: StateCreator<RadarState, [], [], GameSlice> = (set, get) => ({
  collection: null,
  threatStates: {},
  analyzing: null,
  reveal: null,
  claimError: null,

  loadCollection: async () => {
    set({ collection: await fetchCollection() })
  },

  clearGame: () =>
    set({ collection: null, threatStates: {}, analyzing: null, reveal: null, claimError: null }),

  ensureThreatState: async (threatId) => {
    if (get().threatStates[threatId]) return
    const state = await fetchThreatAnalysisState(threatId)
    set((s) => ({ threatStates: { ...s.threatStates, [threatId]: state } }))
  },

  analyze: async (threatId, kind) => {
    // One analysis at a time — the overlay is a single global surface.
    if (get().analyzing) return
    set({ analyzing: { threatId, kind }, reveal: null, claimError: null })

    await new Promise((resolve) => setTimeout(resolve, analysisDelayMs()))

    try {
      const res = await postAnalysis(threatId, kind)
      // The collection here is still the pre-win snapshot (loadCollection below
      // hasn't resolved), so it tells us whether this card was already owned.
      const had = get().collection?.cards.find((c) => c.card_id === res.card_id)
      set({
        analyzing: null,
        reveal: { cardId: res.card_id, kind, isNew: !had, count: (had?.count ?? 0) + 1 },
      })
      void get().loadCollection().catch(() => {})
    } catch (e) {
      const taken = e instanceof ApiError && e.status === 409
      set({ analyzing: null, claimError: taken ? 'taken' : 'error' })
    }
    // Refresh the claim state either way (a win OR a lost race both change it).
    try {
      const state = await fetchThreatAnalysisState(threatId)
      set((s) => ({ threatStates: { ...s.threatStates, [threatId]: state } }))
    } catch {
      // best-effort; the button falls back to its optimistic state
    }
  },

  dismissReveal: () => set({ reveal: null, claimError: null }),
})
