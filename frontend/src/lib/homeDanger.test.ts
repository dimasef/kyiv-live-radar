import { describe, expect, it } from 'vitest'

import type { Home } from '@/store/homeSlice'
import type { Threat, ThreatEvent } from '@/types'

import { currentPositionEvents, homeDangerFor, threatDanger } from './homeDanger'

const HOME: Home = { lat: 50.5, lon: 30.5, radiusKm: 3, origin: 'manual' }
const KM_LAT = 1 / 111.19
const T0 = Date.parse('2026-09-05T20:00:00Z')

function at(minute: number): string {
  return new Date(T0 + minute * 60_000).toISOString()
}

/** A sighting `kmSouth` of home; `validMin` is how long its source's fix lasts. */
function fix(id: number, source_id: number, kmSouth: number, minute: number, validMin: number): ThreatEvent {
  return {
    id,
    threat_id: 1,
    district_id: id,
    event_time: at(minute),
    position_valid_until: at(minute + validMin),
    lat: HOME.lat - kmSouth * KM_LAT,
    lon: HOME.lon,
    source_id,
    raw_text: '',
    confidence: 1,
    decision_source: 'rule',
    manual: false,
  }
}

function threat(events: ThreatEvent[], extra: Partial<Threat> = {}): Threat {
  return {
    id: 1,
    target_type: 'shahed',
    scope: 'district',
    kind: 'track',
    closed_at: null,
    movement_stated: false,
    path_source_id: 5,
    events,
    ...extra,
  } as Threat
}

describe('currentPositionEvents', () => {
  it('keeps each source’s newest fix while it is still valid', () => {
    const t = threat([fix(1, 5, 20, 0, 15), fix(2, 5, 7, 5, 15), fix(3, 12, 1, 5, 5)])
    expect(currentPositionEvents(t, T0 + 6 * 60_000).map((e) => e.id)).toEqual([2, 3])
    expect(currentPositionEvents(t, T0 + 11 * 60_000).map((e) => e.id)).toEqual([2])
  })

  it('falls back to the newest cluster without a clock or validity', () => {
    const t = threat([fix(1, 5, 20, 0, 15), fix(2, 12, 1, 5, 5)])
    expect(currentPositionEvents(t).map((e) => e.id)).toEqual([2])
    const legacy = threat(t.events.map((e) => ({ ...e, position_valid_until: null })))
    expect(currentPositionEvents(legacy, T0 + 60 * 60_000).map((e) => e.id)).toEqual([2])
  })
})

describe('threatDanger', () => {
  it('is danger on the echo’s fix near home and names it as the trigger', () => {
    const t = threat([fix(1, 5, 20, 0, 15), fix(2, 5, 7, 5, 15), fix(3, 12, 1, 5, 5)])
    expect(threatDanger(t, HOME, [], T0 + 6 * 60_000)).toEqual({ level: 'danger', triggerEventId: 3 })
  })

  it('lets a stale echo fix expire while the narrator is still placed', () => {
    const t = threat([fix(1, 5, 20, 0, 15), fix(2, 12, 1, 2, 5), fix(3, 5, 7, 10, 15)])
    expect(threatDanger(t, HOME, [], T0 + 10.5 * 60_000).level).toBe('warning')
  })

  it('keeps a quiet narrator’s fix within its window', () => {
    const t = threat([fix(1, 5, 20, 0, 15), fix(2, 5, 1, 5, 15)])
    expect(threatDanger(t, HOME, [], T0 + 10 * 60_000).level).toBe('danger')
  })
})

describe('homeDangerFor', () => {
  it('reports the worst level and every threat that contributes', () => {
    const near = threat([fix(1, 5, 20, 0, 15), fix(2, 5, 1, 5, 15)])
    const far = threat([fix(3, 5, 40, 0, 15)], { id: 2 })
    const r = homeDangerFor({ 1: near, 2: far }, HOME, [], T0 + 6 * 60_000)
    expect(r.worst).toBe('danger')
    expect(Object.keys(r.byThreat)).toEqual(['1'])
  })
})
