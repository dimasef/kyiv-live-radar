import { describe, expect, it } from 'vitest'

import type { ThreatAnalysisState } from '@/api'

import { analyzeButtonState } from './analyzeButtonState'

const free: ThreatAnalysisState = {
  track_taken: false,
  remains_taken: false,
  mine_track: null,
  mine_remains: null,
}

const call = (over: Partial<Parameters<typeof analyzeButtonState>[0]> = {}) =>
  analyzeButtonState({ kind: 'track', state: free, failed: false, busy: false, ...over })

describe('analyzeButtonState', () => {
  it('offers the action on a target nobody has claimed', () => {
    expect(call()).toBe('available')
  })

  it('reports the slot taken by someone else, and collected when it was us', () => {
    expect(call({ state: { ...free, track_taken: true } })).toBe('taken')
    expect(call({ state: { ...free, track_taken: true, mine_track: 8 } })).toBe('collected')
  })

  it('reads the remains slot, not the track slot, for a remains analysis', () => {
    const state = { ...free, track_taken: true, remains_taken: false }
    expect(call({ kind: 'remains', state })).toBe('available')
    expect(call({ kind: 'track', state })).toBe('taken')
  })

  // The regression this function exists for: an unknown claim state used to
  // fall through to 'available', so an already-claimed target offered "Аналіз"
  // for a frame and then swapped it for "Перевірено".
  it('never offers the action before the claim state has loaded', () => {
    expect(call({ state: undefined })).toBe('checking')
  })

  it('falls through to the action if the claim state could not be fetched', () => {
    // Otherwise a network blip would strand the placeholder forever; the
    // server's 409 remains the authority on who actually won the slot.
    expect(call({ state: undefined, failed: true })).toBe('available')
  })

  it('shows progress while this target is being analysed, even before load', () => {
    expect(call({ busy: true })).toBe('busy')
    expect(call({ busy: true, state: undefined })).toBe('busy')
  })
})
