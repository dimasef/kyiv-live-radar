import { describe, expect, it } from 'vitest'

import type { Threat, ThreatEvent } from '@/types'

import { echoPoints, hasMovement, trackPoints } from './track'

const T = '2026-08-23T19:05:03Z'

const ev = (lat: number, lon: number, event_time = T): ThreatEvent =>
  ({ lat, lon, event_time }) as ThreatEvent

const threat = (events: ThreatEvent[], movement_stated = false): Threat =>
  ({ events, movement_stated }) as Threat

describe('hasMovement', () => {
  it('sees movement when located sightings span two timestamps', () => {
    expect(
      hasMovement(threat([ev(51.1, 31.8), ev(51.4, 32.1, '2026-08-23T19:07:00Z')])),
    ).toBe(true)
  })

  it('treats a same-timestamp multi-district message as an enumeration', () => {
    // "по Дарницькому та Соломʼянському" — places a drone is near, not a route.
    expect(hasMovement(threat([ev(50.4, 30.6), ev(50.45, 30.5)]))).toBe(false)
  })

  it('draws a vector for a same-timestamp track whose path was STATED', () => {
    // «Мамекине на Смяч»: one message, two events, one timestamp — the case
    // that used to render as a bare dot.
    expect(hasMovement(threat([ev(52.0, 33.0), ev(52.1, 33.2)], true))).toBe(true)
  })

  it('needs two distinct points even when a path was stated', () => {
    expect(hasMovement(threat([ev(52.0, 33.0)], true))).toBe(false)
    expect(hasMovement(threat([ev(52.0, 33.0), ev(52.0, 33.0)], true))).toBe(false)
  })

  it('ignores events with no coordinates', () => {
    const nowhere = { lat: null, lon: null, event_time: '2026-08-23T19:09:00Z' } as ThreatEvent
    expect(hasMovement(threat([ev(52.0, 33.0), nowhere]))).toBe(false)
  })
})

describe('trackPoints', () => {
  it('drops consecutive repeats so a chained callout has no zero-length leg', () => {
    // «Мамекине на Смяч» then «Смяч на Гремʼяч» — Смяч is the end of one leg
    // and the start of the next, and must appear once.
    const pts = trackPoints(
      threat([ev(52.0, 33.0), ev(52.1, 33.2), ev(52.1, 33.2), ev(52.3, 33.3)]),
    )
    expect(pts).toEqual([
      { lat: 52.0, lon: 33.0 },
      { lat: 52.1, lon: 33.2 },
      { lat: 52.3, lon: 33.3 },
    ])
  })
})

describe('path source', () => {
  const sighting = (
    lat: number,
    lon: number,
    source_id: number,
    event_time: string,
    manual = false,
  ): ThreatEvent => ({ lat, lon, source_id, event_time, manual }) as ThreatEvent

  const narrated: Threat = {
    path_source_id: 5,
    movement_stated: false,
    events: [
      sighting(50.40, 30.50, 5, '2026-08-30T09:41:00Z'),
      sighting(50.48, 30.62, 12, '2026-08-30T09:41:30Z'),
      sighting(50.44, 30.55, 5, '2026-08-30T09:44:00Z'),
      sighting(50.30, 30.70, 13, '2026-08-30T09:44:20Z'),
      sighting(50.47, 30.58, 5, '2026-08-30T09:47:00Z'),
    ],
  } as unknown as Threat

  it('draws the polyline from the path source only', () => {
    expect(trackPoints(narrated)).toEqual([
      { lat: 50.4, lon: 30.5 },
      { lat: 50.44, lon: 30.55 },
      { lat: 50.47, lon: 30.58 },
    ])
  })

  it('keeps the other sources as echo', () => {
    expect(echoPoints(narrated).map(({ lat, lon }) => ({ lat, lon }))).toEqual([
      { lat: 50.48, lon: 30.62 },
      { lat: 50.3, lon: 30.7 },
    ])
  })

  it('draws every sighting when no path source is set', () => {
    const legacy = { ...narrated, path_source_id: null } as unknown as Threat
    expect(trackPoints(legacy)).toHaveLength(5)
    expect(echoPoints(legacy)).toEqual([])
  })

  it('draws a hand-placed sighting with the path whichever source it came from', () => {
    const t = {
      ...narrated,
      events: [...narrated.events, sighting(50.5, 30.6, 12, '2026-08-30T09:49:00Z', true)],
    } as unknown as Threat
    expect(trackPoints(t)).toHaveLength(4)
    expect(echoPoints(t)).toHaveLength(2)
  })

  it('reads movement off the path, not the echo', () => {
    const echoOnlyMoves = {
      path_source_id: 5,
      movement_stated: false,
      events: [
        sighting(50.4, 30.5, 5, '2026-08-30T09:41:00Z'),
        sighting(50.48, 30.62, 12, '2026-08-30T09:41:30Z'),
        sighting(50.3, 30.7, 12, '2026-08-30T09:44:20Z'),
      ],
    } as unknown as Threat
    expect(hasMovement(echoOnlyMoves)).toBe(false)
  })
})
