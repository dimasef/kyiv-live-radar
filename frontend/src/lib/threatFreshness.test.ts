import { describe, expect, it } from 'vitest'

import type { Threat, ThreatEvent } from '@/types'

import {
  fadeFactor,
  isQuiet,
  lastSeenMs,
  minutesSinceSeen,
  stalePhase,
} from './threatFreshness'

const T0 = Date.parse('2026-08-18T22:00:00Z')
const MIN = 60_000

function threat(over: Partial<Threat> = {}): Threat {
  return {
    id: 1,
    created_at: new Date(T0).toISOString(),
    target_type: 'shahed',
    status: 'tracking',
    kind: 'track',
    closed_reason: null,
    scope: 'district',
    incident_id: null,
    target_count: 1,
    closed_at: null,
    corroboration_count: 1,
    has_conflict: false,
    confidence: 0.5,
    last_event_at: new Date(T0).toISOString(),
    stale_at: new Date(T0 + 20 * MIN).toISOString(),
    events: [],
    ...over,
  } as Threat
}

function event(iso: string): ThreatEvent {
  return { id: 1, district_id: 1, raw_text: '', event_time: iso } as ThreatEvent
}

describe('stalePhase', () => {
  it('runs 0 → 1 across the server-declared window', () => {
    const t = threat()
    expect(stalePhase(t, T0)).toBe(0)
    expect(stalePhase(t, T0 + 10 * MIN)).toBeCloseTo(0.5)
    expect(stalePhase(t, T0 + 20 * MIN)).toBeCloseTo(1)
  })

  it('keeps growing past 1 — the sweeper closes up to a tick late', () => {
    expect(stalePhase(threat(), T0 + 25 * MIN)).toBeCloseTo(1.25)
  })

  it('follows the per-type window the server sent, not a client constant', () => {
    // District ballistic: 5 minutes, so it is fully stale 4x sooner.
    const ballistic = threat({
      target_type: 'ballistic',
      stale_at: new Date(T0 + 5 * MIN).toISOString(),
    })
    expect(stalePhase(ballistic, T0 + 5 * MIN)).toBeCloseTo(1)
    expect(stalePhase(threat(), T0 + 5 * MIN)).toBeCloseTo(0.25)
  })
})

describe('fadeFactor', () => {
  it('holds full brightness while the target is fresh', () => {
    expect(fadeFactor(threat(), T0)).toBe(1)
    expect(fadeFactor(threat(), T0 + 7 * MIN)).toBe(1) // p = 0.35, the hold point
  })

  it('fades monotonically to the floor as the auto-close arrives', () => {
    const t = threat()
    const mid = fadeFactor(t, T0 + 14 * MIN)
    expect(mid).toBeLessThan(1)
    expect(mid).toBeGreaterThan(0.25)
    expect(fadeFactor(t, T0 + 20 * MIN)).toBeCloseTo(0.25)
  })

  it('never goes below the floor, however long the sweeper takes', () => {
    // A target must stay visible (and clickable) while it is still formally open.
    expect(fadeFactor(threat(), T0 + 90 * MIN)).toBeCloseTo(0.25)
  })

  it('keeps an inspected target legible', () => {
    expect(fadeFactor(threat(), T0 + 20 * MIN, true)).toBeCloseTo(0.85)
  })

  it('never fades an impact — a strike is a fact, not a stale target', () => {
    const impact = threat({ kind: 'impact', status: 'impact' })
    expect(fadeFactor(impact, T0 + 60 * MIN)).toBe(1)
    expect(isQuiet(impact, T0 + 60 * MIN)).toBe(false)
  })

  it('leaves a closed track alone — its exit is a CSS animation', () => {
    const closed = threat({ closed_at: new Date(T0 + 20 * MIN).toISOString(), status: 'lost' })
    expect(fadeFactor(closed, T0 + 21 * MIN)).toBe(1)
    expect(isQuiet(closed, T0 + 21 * MIN)).toBe(false)
  })
})

describe('isQuiet', () => {
  it('flips at halfway to the auto-close', () => {
    const t = threat()
    expect(isQuiet(t, T0 + 9 * MIN)).toBe(false)
    expect(isQuiet(t, T0 + 10 * MIN)).toBe(true)
  })
})

describe('fallback when the payload predates the freshness fields', () => {
  it('ages by the newest event and the default window', () => {
    const legacy = threat({
      last_event_at: null,
      stale_at: null,
      events: [event(new Date(T0).toISOString()), event(new Date(T0 + 4 * MIN).toISOString())],
    })
    expect(lastSeenMs(legacy)).toBe(T0 + 4 * MIN)
    // 20-minute default from the last event -> halfway 10 minutes later.
    expect(stalePhase(legacy, T0 + 14 * MIN)).toBeCloseTo(0.5)
  })

  it('falls back to created_at for an eventless legacy row', () => {
    expect(lastSeenMs(threat({ last_event_at: null, stale_at: null }))).toBe(T0)
  })
})

describe('zone-less timestamps', () => {
  it('reads a missing offset as UTC, not as browser-local time', () => {
    // The bug this guards: Date.parse treats an offset-less ISO string as local,
    // so one dropped 'Z' shifted every age by the viewer's UTC offset (a Kyiv
    // client showed "186 хв тому" for a 6-minute-old sighting).
    const naive = threat({
      last_event_at: '2026-08-18T22:00:00',
      stale_at: '2026-08-18T22:20:00',
    })
    expect(lastSeenMs(naive)).toBe(T0)
    expect(minutesSinceSeen(naive, T0 + 6 * MIN)).toBe(6)
    expect(stalePhase(naive, T0 + 10 * MIN)).toBeCloseTo(0.5)
  })
})

describe('minutesSinceSeen', () => {
  it('floors and never goes negative', () => {
    expect(minutesSinceSeen(threat(), T0 + 5.9 * MIN)).toBe(5)
    // A device clock behind the server would otherwise report "-3 min ago".
    expect(minutesSinceSeen(threat(), T0 - 3 * MIN)).toBe(0)
  })
})
