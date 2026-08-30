import { describe, expect, it } from 'vitest'

import { regionHoverStyle, regionStyle } from './regionStyle'

/** --phosphor in index.css. Leaflet paints SVG attributes rather than CSS
 * variables, so the value is duplicated in regionStyle; this is what keeps the
 * two in step. */
const PHOSPHOR = '#22d3ee'

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

  it('never paints a RESTING oblast in the app accent', () => {
    // The regression this locks down. --phosphor means "live threat data"
    // everywhere else on this map, so an oblast wearing it permanently read as
    // something happening there rather than as a setting — readers who had
    // never opened this layer took their own region lighting up for an alert.
    // State is the badge's job now (regionBadge); the outline is geography.
    for (const style of [home, inFeed, outOfFeed, pending]) {
      expect(style.color).not.toBe(PHOSPHOR)
      expect(style.fillColor).not.toBe(PHOSPHOR)
    }
  })

  it('separates the three states by weight as well as by grey', () => {
    // Greys this close cannot carry the distinction on hue alone, and one of
    // the three has to survive being read on a phone in daylight.
    expect(home.weight).toBeGreaterThan(inFeed.weight!)
    expect(inFeed.weight).toBeGreaterThan(outOfFeed.weight!)
  })
})

describe('oblast hover', () => {
  const hover = regionHoverStyle()

  it('is the one place the accent survives on this layer', () => {
    // And it survives because it is TRANSIENT: phosphor under the cursor reads
    // as "this responds to you", where phosphor sitting on a region read as
    // "something is happening there".
    expect(hover.color).toBe(PHOSPHOR)
  })

  it('lifts an out-of-feed region clear of its resting state', () => {
    expect(hover.opacity).toBeGreaterThan(outOfFeed.opacity!)
  })

  it('leaves the dashed edge of a pending region alone', () => {
    // setStyle MERGES — an undefined dashArray here keeps "no coverage yet"
    // readable while the region is hovered.
    expect(hover.dashArray).toBeUndefined()
  })
})
