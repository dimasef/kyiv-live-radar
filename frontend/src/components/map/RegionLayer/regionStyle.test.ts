import { describe, expect, it } from 'vitest'

import { regionHoverStyle, regionStyle } from './regionStyle'

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

  it('paints a followed region in the app accent', () => {
    // --phosphor in index.css. Leaflet paints SVG attributes, so the value is
    // duplicated in regionStyle and this is what keeps the two in step.
    expect(home.color).toBe('#22d3ee')
  })
})

describe('oblast hover', () => {
  const hover = regionHoverStyle()

  it('previews the accent an added region would get', () => {
    expect(hover.color).toBe(home.color)
  })

  it('stays below a region that is already in the feed', () => {
    // Otherwise pointing at a region would look louder than actually adding it.
    expect(hover.opacity).toBeLessThan(inFeed.opacity!)
  })

  it('lifts an out-of-feed region without shouting', () => {
    expect(hover.opacity).toBeGreaterThan(outOfFeed.opacity!)
  })

  it('leaves the dashed edge of a pending region alone', () => {
    // setStyle MERGES — an undefined dashArray here keeps "no coverage yet"
    // readable while the region is hovered.
    expect(hover.dashArray).toBeUndefined()
  })
})
