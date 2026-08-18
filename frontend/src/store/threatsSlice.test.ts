import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Threat } from '@/types'

import { createThreatsSlice } from './threatsSlice'
import type { RadarState } from './types'

/** Drive the slice without the rest of the store (no leaflet, no network). */
function makeStore(overrides: Partial<RadarState> = {}) {
  let state = {} as RadarState
  const set = (patch: unknown) => {
    const next = typeof patch === 'function' ? (patch as (s: RadarState) => object)(state) : patch
    state = { ...state, ...(next as object) } as RadarState
  }
  const get = () => state
  state = {
    ...createThreatsSlice(set as never, get as never, {} as never),
    ...overrides,
  } as RadarState
  return { get, set }
}

function closedThreat(over: Partial<Threat> = {}): Threat {
  return {
    id: 7,
    created_at: '2026-08-18T22:00:00Z',
    target_type: 'shahed',
    status: 'destroyed',
    kind: 'track',
    closed_reason: 'destroyed',
    scope: 'district',
    incident_id: null,
    target_count: 1,
    closed_at: '2026-08-18T22:05:00Z',
    corroboration_count: 1,
    has_conflict: false,
    confidence: 0.5,
    events: [],
    ...over,
  } as Threat
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('closed-track eviction', () => {
  it('fades for the last 700ms, then drops the track', () => {
    const { get } = makeStore()
    get().applyThreatMessage({ type: 'status', threat: closedThreat() })
    expect(get().threats[7]).toBeDefined()

    vi.advanceTimersByTime(5299) // still in the plain linger
    expect(get().leavingThreatIds).toEqual([])

    vi.advanceTimersByTime(2) // 5301ms — the exit fade starts
    expect(get().leavingThreatIds).toEqual([7])
    expect(get().threats[7]).toBeDefined() // still drawn while it fades

    vi.advanceTimersByTime(700)
    expect(get().threats[7]).toBeUndefined()
    expect(get().leavingThreatIds).toEqual([])
  })

  it('never evicts an impact — a strike location persists', () => {
    const { get } = makeStore()
    get().applyThreatMessage({
      type: 'status',
      threat: closedThreat({ status: 'impact', kind: 'impact' }),
    })
    vi.advanceTimersByTime(60_000)
    expect(get().threats[7]).toBeDefined()
  })

  it('drops a dismissed track at once, with no fade', () => {
    const { get } = makeStore()
    get().applyThreatMessage({ type: 'status', threat: closedThreat({ status: 'dismissed' }) })
    expect(get().threats[7]).toBeUndefined()
    expect(get().leavingThreatIds).toEqual([])
  })
})

describe('a target being read is never yanked away', () => {
  it('holds the whole exit while its popup is open, and releases on close', () => {
    // The reported bug: clicking a destroyed target and watching it dissolve a
    // few seconds later, mid-read.
    const { get } = makeStore()
    get().applyThreatMessage({ type: 'status', threat: closedThreat() })
    get().setOpenPopupThreat(7)

    vi.advanceTimersByTime(30_000)
    expect(get().threats[7]).toBeDefined()
    expect(get().leavingThreatIds).toEqual([]) // not even fading

    get().setOpenPopupThreat(null)
    vi.advanceTimersByTime(700) // the retry notices it's free, fade starts
    expect(get().leavingThreatIds).toEqual([7])
    vi.advanceTimersByTime(700)
    expect(get().threats[7]).toBeUndefined()
  })

  it('holds while the track is the inspected one', () => {
    // The inspected copy is deliberately independent and permanent, so the live
    // copy underneath must not fade out from under it either.
    const { get } = makeStore()
    get().applyThreatMessage({ type: 'status', threat: closedThreat() })
    get().inspectThreat(closedThreat())

    vi.advanceTimersByTime(30_000)
    expect(get().threats[7]).toBeDefined()
    expect(get().leavingThreatIds).toEqual([])

    get().clearInspection()
    vi.advanceTimersByTime(1400)
    expect(get().threats[7]).toBeUndefined()
  })
})
