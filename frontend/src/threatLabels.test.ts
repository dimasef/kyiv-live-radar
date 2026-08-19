import { describe, expect, it } from 'vitest'

import { STATUS_COLORS } from '@/theme'
import { threatChip } from '@/threatLabels'
import type { Threat } from '@/types'

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

const closed = (reason: Threat['closed_reason'], status: Threat['status'] = 'lost') =>
  threat({ status, closed_reason: reason, closed_at: '2026-08-18T22:10:00Z' })

describe('threatChip', () => {
  it('reads live states off the status', () => {
    expect(threatChip(threat())).toEqual({
      labelKey: 'status.tracking',
      color: STATUS_COLORS.confirmed,
    })
    expect(threatChip(threat({ status: 'unconfirmed' })).color).toBe(STATUS_COLORS.unconfirmed)
  })

  it('paints a shot-down target with the good-news green', () => {
    expect(threatChip(closed('destroyed', 'destroyed'))).toEqual({
      labelKey: 'status.destroyed',
      color: STATUS_COLORS.clear,
    })
  })

  it('separates an official відбій from plain silence', () => {
    // status is 'lost' for all three closings, so only closed_reason can tell
    // "someone declared it over" from "nobody knows what happened".
    expect(threatChip(closed('all_clear'))).toEqual({
      labelKey: 'status.allClear',
      color: STATUS_COLORS.clear,
    })
    for (const reason of ['stale', 'stand_down'] as const) {
      expect(threatChip(closed(reason))).toEqual({
        labelKey: 'status.lost',
        color: STATUS_COLORS.unseen,
      })
    }
  })

  it('keeps an impact an impact, whatever it was closed with', () => {
    // Impacts are closed on creation; a closed_reason must not turn a strike
    // into an "all clear".
    const impact = threat({ status: 'impact', kind: 'impact', closed_at: '2026-08-18T22:00:00Z' })
    expect(threatChip(impact).labelKey).toBe('status.impact')
    expect(threatChip({ ...impact, closed_reason: 'all_clear' }).labelKey).toBe('status.impact')
    expect(threatChip(impact).color).toBe(STATUS_COLORS.impact)
  })
})
