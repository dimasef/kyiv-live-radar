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

/** How long the "analysing…" animation runs before the card drops — a random
 * 3–10s, per the design (the suspense IS the point; keep it passive so the user
 * can put the phone down). */
function analysisDelayMs(): number {
  return 3000 + Math.floor(Math.random() * 7001)
}

export interface GameSlice {
  /** The current user's card collection (null until first load / logged out). */
  collection: Collection | null
  /** Per-target global claim state, cached as targets are inspected. */
  threatStates: Record<number, ThreatAnalysisState>
  /** The analysis currently running (drives the scanning overlay), or null. */
  analyzing: { threatId: number; kind: AnalysisKind } | null
  /** A freshly-won card to show in the reveal modal, or null. */
  reveal: { cardId: number; kind: AnalysisKind } | null
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
      set({ analyzing: null, reveal: { cardId: res.card_id, kind } })
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
