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

describe('news about an already-gone track', () => {
  it('reaches the feed without putting the dot back on the map', () => {
    // A «збито» that lands after the sweeper already retired the target: the
    // backend relabels that close and broadcasts it as an EVENT so the feed
    // shows the interception. The map must not take it — the track was evicted
    // long ago, and re-adding it would flash the dot back for the whole linger.
    const { get } = makeStore()
    get().applyThreatMessage({
      type: 'event',
      threat: closedThreat({ closed_reason: 'destroyed' }),
      event: { id: 9, threat_id: 7 } as never,
    })
    expect(get().threats[7]).toBeUndefined()
    expect(get().log).toHaveLength(1)
    expect(get().log[0].threat.closed_reason).toBe('destroyed')
    // ...and nothing was scheduled that could make it appear later.
    vi.advanceTimersByTime(30_000)
    expect(get().threats[7]).toBeUndefined()
  })

  it('still updates a track that is currently playing its exit', () => {
    const { get } = makeStore()
    get().applyThreatMessage({ type: 'status', threat: closedThreat({ closed_reason: 'stale' }) })
    get().applyThreatMessage({
      type: 'event',
      threat: closedThreat({ closed_reason: 'destroyed' }),
      event: { id: 9, threat_id: 7 } as never,
    })
    expect(get().threats[7]?.closed_reason).toBe('destroyed')
  })
})

describe('the feed follows the track it embeds', () => {
  const entry = (threat: Threat) => ({ event: { id: 1, threat_id: threat.id } as never, threat })

  it('re-types a feed card when the track is retyped', () => {
    // The reported bug: an admin retype (БПЛА -> реактивний) changed the map at
    // once but the feed only after a reload, because each card holds its own
    // snapshot of the track.
    const original = closedThreat({ status: 'tracking', closed_at: null, closed_reason: null })
    const { get } = makeStore({ log: [entry(original)] } as never)

    get().applyThreatMessage({
      type: 'status',
      threat: { ...original, target_type: 'jet_drone' },
    })
    expect(get().log[0].threat.target_type).toBe('jet_drone')
  })

  it('keeps the inspected copy in sync, event history and all', () => {
    const original = closedThreat({ status: 'tracking', closed_at: null, closed_reason: null })
    const { get } = makeStore()
    get().inspectThreat({ ...original, events: [{ id: 4 } as never] })

    get().applyThreatMessage({ type: 'status', threat: { ...original, target_type: 'ballistic' } })
    expect(get().inspectedThreat?.target_type).toBe('ballistic')
    // A broadcast without the full history must not erase what was fetched.
    expect(get().inspectedThreat?.events).toHaveLength(1)
  })

  it('takes a dismissed track out of the feed too', () => {
    const original = closedThreat({ status: 'tracking', closed_at: null, closed_reason: null })
    const { get } = makeStore({ log: [entry(original)] } as never)

    get().applyThreatMessage({ type: 'status', threat: closedThreat({ status: 'dismissed' }) })
    expect(get().log).toEqual([])
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
