import { describe, expect, it } from 'vitest'

import type { TargetType, Threat } from '@/types'

import { etaMinutes, formatRange, speedRangeOf, TYPE_SPEED_KMH } from './threatSpeed'

function threat(over: Partial<Threat> = {}): Threat {
  return {
    id: 1,
    created_at: '2026-08-18T22:00:00Z',
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
    events: [],
    ...over,
  } as Threat
}

describe('speedRangeOf', () => {
  it('gives an ascending range for every flying type', () => {
    const types: TargetType[] = ['shahed', 'jet_drone', 'missile', 'ballistic']
    for (const target_type of types) {
      const range = speedRangeOf(threat({ target_type }))
      expect(range, target_type).not.toBeNull()
      expect(range!.min).toBeLessThan(range!.max)
      expect(range).toEqual(TYPE_SPEED_KMH[target_type])
    }
  })

  it('says nothing for an unknown type', () => {
    expect(speedRangeOf(threat({ target_type: 'unknown' }))).toBeNull()
  })

  it.each(['destroyed', 'lost', 'dismissed'] as const)('says nothing once %s', (status) => {
    expect(speedRangeOf(threat({ status }))).toBeNull()
  })

  it('says nothing for a closed track or an impact', () => {
    expect(speedRangeOf(threat({ closed_at: '2026-08-18T22:10:00Z' }))).toBeNull()
    expect(speedRangeOf(threat({ kind: 'impact', status: 'impact' }))).toBeNull()
  })
})

describe('etaMinutes', () => {
  it('reads the shorter time off the faster end', () => {
    // 14 km at 150–200 km/h — the screenshot's case.
    expect(etaMinutes(14, { min: 150, max: 200 })).toEqual({ min: 4, max: 6 })
  })

  it('stays 0 when the target arrives inside a minute', () => {
    expect(etaMinutes(14, { min: 1500, max: 3000 })).toEqual({ min: 0, max: 1 })
    expect(etaMinutes(3, { min: 1500, max: 3000 }).max).toBe(0)
  })

  it('collapses to one number when both ends round the same', () => {
    const eta = etaMinutes(10, { min: 700, max: 900 })
    expect(eta).toEqual({ min: 1, max: 1 })
  })
})

describe('formatRange', () => {
  it('collapses an equal range to a single number', () => {
    expect(formatRange(5, 5)).toBe('5')
    expect(formatRange(4, 6)).toBe('4–6')
  })
})
