import { describe, expect, it } from 'vitest'

import { regionStyle } from './regionStyle'

const home = regionStyle({ isHome: true, inFeed: true, active: true })
const inFeed = regionStyle({ isHome: false, inFeed: true, active: true })
const outOfFeed = regionStyle({ isHome: false, inFeed: false, active: true })
const pending = regionStyle({ isHome: false, inFeed: false, active: false })

describe('oblast outline styling', () => {
  it('always paints a fill, however faintly', () => {
    // The fill is the HIT AREA — SVG hit-testing only sees a painted fill, and
    // clicking the middle of an oblast is the whole interaction. A zero here
    // would leave the region reachable by its 1px border alone.
    for (const style of [home, inFeed, outOfFeed, pending]) {
      expect(style.fillOpacity).toBeGreaterThan(0)
    }
  })

  it('keeps the fill invisible on a dark basemap', () => {
    for (const style of [home, inFeed, outOfFeed, pending]) {
      expect(style.fillOpacity).toBeLessThanOrEqual(0.02)
    }
  })

  it('reads home as the loudest and out-of-feed as the quietest', () => {
    expect(home.opacity).toBeGreaterThan(inFeed.opacity!)
    expect(inFeed.opacity).toBeGreaterThan(outOfFeed.opacity!)
  })

  it('tells "not added" apart from "no data yet"', () => {
    expect(outOfFeed.dashArray).toBeUndefined()
    expect(pending.dashArray).toBeTruthy()
  })

  it('gives home and a chosen region the same hue, distinct from the rest', () => {
    expect(inFeed.color).toBe(home.color)
    expect(outOfFeed.color).not.toBe(home.color)
  })
})
