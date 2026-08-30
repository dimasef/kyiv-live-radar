import { describe, expect, it } from 'vitest'

import { edgeMarkerPosition, isInsideBox, outsetInsets, screenBearing } from './edgeProjection'

describe('edgeMarkerPosition', () => {
  // A phone-ish map with the alert banner up top and the feed sheet below.
  const size = { x: 390, y: 780 }
  const insets = { top: 64, right: 12, bottom: 76, left: 12 }
  const pill = { width: 108, height: 30 }

  it('keeps the whole pill inside the safe box, from every direction', () => {
    for (let deg = 0; deg < 360; deg += 5) {
      const { left, top } = edgeMarkerPosition(deg, size, insets, pill)
      expect(left).toBeGreaterThanOrEqual(insets.left - 0.001)
      expect(left + pill.width).toBeLessThanOrEqual(size.x - insets.right + 0.001)
      expect(top).toBeGreaterThanOrEqual(insets.top - 0.001)
      expect(top + pill.height).toBeLessThanOrEqual(size.y - insets.bottom + 0.001)
    }
  })

  it('hangs the pill inward from the side it points past', () => {
    // The reported bug: due west the arrow was clipped off the left edge.
    expect(edgeMarkerPosition(270, size, insets, pill).left).toBeCloseTo(insets.left, 6)
    expect(edgeMarkerPosition(90, size, insets, pill).left).toBeCloseTo(
      size.x - insets.right - pill.width,
      6,
    )
  })

  it('stops above the feed sheet when home is due south', () => {
    // The other reported bug: the pill sat under the collapsed sheet.
    const south = edgeMarkerPosition(180, size, insets, pill)
    expect(south.top).toBeCloseTo(size.y - insets.bottom - pill.height, 6)
    expect(south.left).toBeCloseTo((size.x + insets.left - insets.right - pill.width) / 2, 6)
  })

  it('clears the alert banner when home is due north', () => {
    expect(edgeMarkerPosition(0, size, insets, pill).top).toBeCloseTo(insets.top, 6)
  })

  it('pulls a corner-bound pill in so it never spills sideways', () => {
    // North-east: it rides the top edge, but centring it there would push its
    // right half past the container.
    const ne = edgeMarkerPosition(60, size, insets, pill)
    expect(ne.left + pill.width).toBeLessThanOrEqual(size.x - insets.right + 0.001)
  })

  it('survives a container narrower than the pill itself', () => {
    const tiny = edgeMarkerPosition(90, { x: 40, y: 40 }, insets, pill)
    expect(tiny.left).toBe(insets.left)
    expect(tiny.top).toBe(insets.top)
  })
})

describe('isInsideBox', () => {
  const size = { x: 390, y: 780 }
  const insets = { top: 64, right: 56, bottom: 76, left: 56 }


  it('accepts a point in the clear middle', () => {
    expect(isInsideBox(195, 400, size, insets)).toBe(true)
  })

  it('rejects a point hidden under the feed sheet or the banner', () => {
    expect(isInsideBox(195, size.y - insets.bottom + 1, size, insets)).toBe(false)
    expect(isInsideBox(195, insets.top - 1, size, insets)).toBe(false)
  })
})

describe('outsetInsets', () => {
  // The HomeCompass dead zone: home must clear the visible box by a real
  // distance before the pointer is worth showing. Numbers mirror the component
  // — a phone-ish map, the safe box, and a quarter of the shorter side.
  const size = { x: 390, y: 780 }
  const safe = { top: 64, right: 56, bottom: 76, left: 56 }
  // Mirrors APPEAR_MARGIN_RATIO in HomeCompass — the component can't be imported
  // here (it pulls Leaflet into a DOM-free suite), so the number is restated.
  const margin = 0.35 * Math.min(size.x, size.y) // 136.5
  const zone = outsetInsets(safe, margin)

  it('lets the box run past the container edge', () => {
    // Negative insets are the point: "97 px beyond the left edge" has no
    // expression inside the container.
    expect(zone.left).toBeLessThan(0)
    expect(zone.right).toBeLessThan(0)
  })

  it('still counts a home just off the edge as present', () => {
    // The regression this fixes: at x = 20 home is plainly on screen, yet the
    // bare safe box (left = 56) called it gone and showed a distance to
    // something the operator could see.
    expect(isInsideBox(20, 400, size, safe)).toBe(false)
    expect(isInsideBox(20, 400, size, zone)).toBe(true)
    // Even a little past the edge is still "just up there", not gone.
    expect(isInsideBox(-40, 400, size, zone)).toBe(true)
  })

  it('reports home as gone once it clears the dead zone', () => {
    expect(isInsideBox(-160, 400, size, zone)).toBe(false)
    expect(isInsideBox(size.x + 160, 400, size, zone)).toBe(false)
    expect(isInsideBox(195, -160, size, zone)).toBe(false)
  })

  it('leaves the box unchanged at zero', () => {
    expect(outsetInsets(safe, 0)).toEqual(safe)
  })
})

describe('screenBearing', () => {
  it('reads screen deltas as compass degrees, north being up', () => {
    expect(screenBearing(0, -10)).toBe(0) // straight up
    expect(screenBearing(10, 0)).toBe(90) // right
    expect(screenBearing(0, 10)).toBe(180) // down
    expect(screenBearing(-10, 0)).toBe(-90) // left
  })

  it('agrees with edgeMarkerPosition about which side of the box to sit on', () => {
    const size = { x: 390, y: 780 }
    const insets = { top: 64, right: 12, bottom: 76, left: 12 }
    const pill = { width: 108, height: 30 }
    // Home off the right edge -> the pointer belongs on the right edge.
    const right = edgeMarkerPosition(screenBearing(500, 0), size, insets, pill)
    expect(right.left).toBeCloseTo(size.x - insets.right - pill.width, 6)
    // ...and above -> the top.
    const up = edgeMarkerPosition(screenBearing(0, -500), size, insets, pill)
    expect(up.top).toBeCloseTo(insets.top, 6)
  })
})
