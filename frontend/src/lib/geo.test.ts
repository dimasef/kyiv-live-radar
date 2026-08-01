import { describe, expect, it } from 'vitest'

import { angdiff, bearing, haversineKm, offsetKm, raionIdAt } from './geo'
import type { DistrictBoundary } from '../types'

const KYIV = { lat: 50.45, lon: 30.52 }

describe('bearing', () => {
  it('reads exactly 0 due north', () => {
    expect(bearing(KYIV, { lat: 51.45, lon: 30.52 })).toBeCloseTo(0, 5)
  })

  it('reads just under 90 due east — this is a great-circle INITIAL bearing', () => {
    // Not 90: a great circle to a point on the same parallel leaves slightly
    // north of due east (that is the rhumb-line bearing, a different thing).
    // Pinned so a future "fix" toward a flat 90 has to argue with this test.
    expect(bearing(KYIV, { lat: 50.45, lon: 31.52 })).toBeCloseTo(89.61, 2)
  })

  it('always returns a value in [0, 360) — never a negative angle', () => {
    const west = bearing(KYIV, { lat: 50.45, lon: 29.52 })
    expect(west).toBeGreaterThanOrEqual(0)
    expect(west).toBeLessThan(360)
    expect(west).toBeCloseTo(270.39, 2) // mirror of the eastward case above
  })
})

describe('haversineKm', () => {
  it('is zero for a point against itself', () => {
    expect(haversineKm(KYIV, KYIV)).toBe(0)
  })

  it('is symmetric', () => {
    const b = { lat: 49.84, lon: 24.03 } // Lviv
    expect(haversineKm(KYIV, b)).toBeCloseTo(haversineKm(b, KYIV), 9)
  })

  it('matches the known Kyiv–Lviv great-circle distance', () => {
    // Must match backend geometry.haversine_km — home-danger runs on both sides.
    expect(haversineKm(KYIV, { lat: 49.84, lon: 24.03 })).toBeCloseTo(467.26, 1)
  })
})

describe('angdiff', () => {
  it('takes the short way around the wrap point', () => {
    expect(angdiff(10, 350)).toBe(20)
    expect(angdiff(350, 10)).toBe(-20)
  })

  it('returns +180, not -180, for opposite bearings', () => {
    expect(angdiff(180, 0)).toBe(180)
  })
})

describe('offsetKm', () => {
  it('round-trips back to the origin when the offset is negated', () => {
    const moved = offsetKm(KYIV, 5, 7)
    const back = offsetKm(moved, -5, -7)
    expect(back.lat).toBeCloseTo(KYIV.lat, 6)
    // Longitude is only approximately reversible — the km-per-degree factor is
    // taken at each point's own latitude — so this is a looser bound on purpose.
    expect(back.lon).toBeCloseTo(KYIV.lon, 3)
  })

  it('displaces by the requested distance', () => {
    expect(haversineKm(KYIV, offsetKm(KYIV, 10, 0))).toBeCloseTo(10, 2)
    expect(haversineKm(KYIV, offsetKm(KYIV, 0, 10))).toBeCloseTo(10, 1)
  })
})

describe('raionIdAt', () => {
  // A unit square around (50, 30); GeoJSON rings are [lon, lat].
  const square: DistrictBoundary[] = [
    {
      id: 7,
      name_uk: 'Тест',
      name_en: 'Test',
      geojson: {
        type: 'Polygon',
        coordinates: [
          [
            [29.5, 49.5],
            [30.5, 49.5],
            [30.5, 50.5],
            [29.5, 50.5],
            [29.5, 49.5],
          ],
        ],
      },
    } as DistrictBoundary,
  ]

  it('finds the containing polygon', () => {
    expect(raionIdAt(50, 30, square)).toBe(7)
  })

  it('returns null outside every polygon', () => {
    expect(raionIdAt(48, 30, square)).toBeNull()
    expect(raionIdAt(50, 33, square)).toBeNull()
  })

  it('returns null when there are no boundaries loaded yet', () => {
    expect(raionIdAt(50, 30, [])).toBeNull()
  })
})
