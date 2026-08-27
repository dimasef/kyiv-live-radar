import { describe, expect, it } from 'vitest'

import type { Threat, ThreatEvent } from '@/types'

import { isVisible, trackBox, type LatLonBox } from './viewportCull'

const ev = (lat: number | null, lon: number | null): ThreatEvent =>
  ({ lat, lon, event_time: '2026-08-27T10:00:00Z' }) as ThreatEvent

const threat = (events: ThreatEvent[], extra: Partial<Threat> = {}): Threat =>
  ({ id: 1, events, scope: 'local', ...extra }) as Threat

/** Roughly Kyiv city on screen. */
const KYIV: LatLonBox = { south: 50.2, west: 30.2, north: 50.6, east: 30.9 }

describe('trackBox', () => {
  it('spans the extremes of every located sighting', () => {
    expect(trackBox(threat([ev(51.1, 31.8), ev(50.9, 32.1), ev(51.4, 31.5)]))).toEqual({
      south: 50.9,
      west: 31.5,
      north: 51.4,
      east: 32.1,
    })
  })

  it('ignores sightings the parser could not place', () => {
    expect(trackBox(threat([ev(null, null), ev(50.4, 30.5)]))).toEqual({
      south: 50.4,
      west: 30.5,
      north: 50.4,
      east: 30.5,
    })
  })

  it('is null when nothing is located', () => {
    expect(trackBox(threat([ev(null, null)]))).toBeNull()
    expect(trackBox(threat([]))).toBeNull()
  })
})

describe('isVisible', () => {
  it('keeps a track inside the view', () => {
    expect(isVisible(threat([ev(50.45, 30.52)]), KYIV)).toBe(true)
  })

  it('drops a track that is entirely elsewhere', () => {
    // A Chernihiv-corridor target while the operator is reading Kyiv.
    expect(isVisible(threat([ev(51.5, 31.3), ev(51.6, 31.4)]), KYIV)).toBe(false)
  })

  it('keeps a long track whose ENDS are both off-screen', () => {
    // The regression this shape exists to prevent: testing "is a sighting
    // inside the box" would cull a vector crossing the middle of the view.
    expect(isVisible(threat([ev(50.4, 29.0), ev(50.4, 32.0)]), KYIV)).toBe(true)
  })

  it('keeps a track touching the very edge of the view', () => {
    expect(isVisible(threat([ev(50.6, 30.9)]), KYIV)).toBe(true)
  })

  it('drops a city-wide track — it belongs to the banner, not the map', () => {
    expect(isVisible(threat([ev(50.45, 30.52)], { scope: 'city' }), KYIV)).toBe(false)
  })

  it('drops a track with nothing located to draw', () => {
    expect(isVisible(threat([ev(null, null)]), KYIV)).toBe(false)
  })
})
