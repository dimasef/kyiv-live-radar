import { describe, expect, it } from 'vitest'

import { VIEW_MARGIN_PX, edgePercent, isWellInsideView, screenBearing } from './edgeProjection'

// Per-field, not toEqual: the trig lands cardinals on 7.000000000000001.
function expectAt(actual: { left: number; top: number }, left: number, top: number) {
  expect(actual.left).toBeCloseTo(left, 9)
  expect(actual.top).toBeCloseTo(top, 9)
}

describe('edgePercent', () => {
  it('puts north at top-centre and south at bottom-centre', () => {
    expectAt(edgePercent(0), 50, 7)
    expectAt(edgePercent(180), 50, 93)
  })

  it('puts east at right-centre and west at left-centre', () => {
    expectAt(edgePercent(90), 93, 50)
    expectAt(edgePercent(270), 7, 50)
  })

  it('lands a diagonal bearing in the matching corner', () => {
    const ne = edgePercent(45)
    expect(ne.left).toBeGreaterThan(50)
    expect(ne.top).toBeLessThan(50)
    const sw = edgePercent(225)
    expect(sw.left).toBeLessThan(50)
    expect(sw.top).toBeGreaterThan(50)
  })

  it('always stays inside the container, so a wedge is never clipped', () => {
    for (let deg = 0; deg < 360; deg += 5) {
      const { left, top } = edgePercent(deg)
      expect(left).toBeGreaterThanOrEqual(0)
      expect(left).toBeLessThanOrEqual(100)
      expect(top).toBeGreaterThanOrEqual(0)
      expect(top).toBeLessThanOrEqual(100)
    }
  })

  it('wraps: 360 is the same place as 0', () => {
    const a = edgePercent(0)
    const b = edgePercent(360)
    expect(b.left).toBeCloseTo(a.left, 9)
    expect(b.top).toBeCloseTo(a.top, 9)
  })
})

describe('isWellInsideView', () => {
  const size = { x: 800, y: 600 }

  it('accepts a point comfortably inside', () => {
    expect(isWellInsideView(400, 300, size)).toBe(true)
  })

  it('rejects a point in the margin band, so the wedge stays instead', () => {
    expect(isWellInsideView(VIEW_MARGIN_PX - 1, 300, size)).toBe(false)
    expect(isWellInsideView(400, size.y - VIEW_MARGIN_PX + 1, size)).toBe(false)
  })

  it('treats the margin itself as inside (boundary is inclusive)', () => {
    expect(isWellInsideView(VIEW_MARGIN_PX, VIEW_MARGIN_PX, size)).toBe(true)
  })

  it('rejects the off-screen sentinel used for coordinate-less axes', () => {
    expect(isWellInsideView(-9999, -9999, size)).toBe(false)
  })
})

describe('screenBearing', () => {
  it('reads screen deltas as compass degrees, north being up', () => {
    expect(screenBearing(0, -10)).toBe(0) // straight up
    expect(screenBearing(10, 0)).toBe(90) // right
    expect(screenBearing(0, 10)).toBe(180) // down
    expect(screenBearing(-10, 0)).toBe(-90) // left
  })

  it('agrees with edgePercent about which side of the box to sit on', () => {
    // Home off the right edge -> the pointer belongs on the right edge.
    const right = edgePercent(screenBearing(500, 0))
    expect(right.left).toBeGreaterThan(50)
    // ...and above -> the top.
    const up = edgePercent(screenBearing(0, -500))
    expect(up.top).toBeLessThan(50)
  })
})
