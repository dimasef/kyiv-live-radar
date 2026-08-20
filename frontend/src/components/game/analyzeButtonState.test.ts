import { describe, expect, it } from 'vitest'

import type { ThreatAnalysisState } from '@/api'
import type { Threat } from '@/types'

import { analyzeButtonState, showsAnalyzeAffordance } from './analyzeButtonState'

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

const HOUR = 3_600_000

function threat(over: Partial<Threat> = {}): Threat {
  const seen = new Date(Date.now() - HOUR).toISOString()
  return {
    id: 1,
    target_type: 'shahed',
    status: 'tracking',
    scope: 'district',
    closed_at: null,
    closed_reason: null,
    last_event_at: seen,
    created_at: seen,
    events: [],
    ...over,
  } as Threat
}

// The popup draws a separator above this section, so "renders nothing" and
// "renders a hairline and nothing else" are different bugs — the second one
// shipped, hanging a rule off the bottom of every «Невідомо» popup.
describe('showsAnalyzeAffordance', () => {
  it('is true for a live analysable target', () => {
    expect(showsAnalyzeAffordance(threat(), true)).toBe(true)
  })

  it('is false for a target type that is never analysable', () => {
    expect(showsAnalyzeAffordance(threat({ target_type: 'unknown' }), true)).toBe(false)
  })

  it('is false for a city-wide threat — there is no place to search', () => {
    expect(showsAnalyzeAffordance(threat({ scope: 'city' }), true)).toBe(false)
  })

  it('is false for anyone signed out, however analysable the target', () => {
    expect(showsAnalyzeAffordance(threat(), false)).toBe(false)
  })

  it('stays true once the debris goes cold — that is a chip, not nothing', () => {
    const cold = new Date(Date.now() - 13 * HOUR).toISOString()
    const stale = threat({ status: 'destroyed', last_event_at: cold, created_at: cold })
    expect(showsAnalyzeAffordance(stale, true)).toBe(true)
  })
})
