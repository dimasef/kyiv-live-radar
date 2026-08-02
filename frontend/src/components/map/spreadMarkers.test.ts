import { describe, expect, it } from 'vitest'

import { spreadOverlapping, type PixelPoint } from './spreadMarkers'

const at = (id: string, x: number, y: number): PixelPoint => ({ id, x, y })

/** Closest approach between any two markers once their offsets are applied. */
function minSeparation(points: PixelPoint[], offsets: Map<string, [number, number]>): number {
  const placed = points.map((p) => {
    const [dx, dy] = offsets.get(p.id) ?? [0, 0]
    return { x: p.x + dx, y: p.y + dy }
  })
  let min = Infinity
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      min = Math.min(min, Math.hypot(placed[i].x - placed[j].x, placed[i].y - placed[j].y))
    }
  }
  return min
}

describe('spreadOverlapping', () => {
  it('leaves markers that are already apart exactly where they are', () => {
    const points = [at('me', 100, 100), at('7', 400, 400)]
    expect(spreadOverlapping(points, { anchorId: 'me' }).size).toBe(0)
  })

  it('keeps the anchor put and moves the contact off it', () => {
    // The reported bug: a contact in the same building hid the user's own home.
    const points = [at('me', 100, 100), at('7', 102, 101)]
    const offsets = spreadOverlapping(points, { minGap: 26, anchorId: 'me' })
    expect(offsets.get('me')).toEqual([0, 0])
    expect(minSeparation(points, offsets)).toBeGreaterThanOrEqual(24)
  })

  it('separates a whole pile of contacts, from each other as well as the anchor', () => {
    const points = [
      at('me', 200, 200),
      at('1', 201, 200),
      at('2', 199, 203),
      at('3', 204, 198),
      at('4', 200, 201),
    ]
    const offsets = spreadOverlapping(points, { minGap: 26, anchorId: 'me' })
    expect(offsets.get('me')).toEqual([0, 0])
    expect(minSeparation(points, offsets)).toBeGreaterThanOrEqual(24)
  })

  it('spreads a cluster with no anchor in it', () => {
    const points = [at('7', 300, 300), at('8', 302, 301)]
    const offsets = spreadOverlapping(points, { minGap: 26, anchorId: 'me' })
    expect(minSeparation(points, offsets)).toBeGreaterThanOrEqual(24)
  })

  it('is stable regardless of input order, so icons never swap places', () => {
    const points = [at('me', 100, 100), at('7', 101, 100), at('9', 100, 102)]
    const a = spreadOverlapping(points, { anchorId: 'me' })
    const b = spreadOverlapping([...points].reverse(), { anchorId: 'me' })
    expect([...a.entries()].sort()).toEqual([...b.entries()].sort())
  })

  it('keeps far-apart clusters independent', () => {
    const points = [at('me', 100, 100), at('7', 101, 101), at('8', 900, 900)]
    const offsets = spreadOverlapping(points, { anchorId: 'me' })
    expect(offsets.has('8')).toBe(false)
  })
})
