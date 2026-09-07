import { describe, expect, it } from 'vitest'

import {
  paneZIndex,
  ZONE_ALL_CLEAR_PANE,
  ZONE_GLOW_PANE,
  ZONE_OUTLINE_PANE,
} from './zonePanes'

const above = (a: Parameters<typeof paneZIndex>[0], b: Parameters<typeof paneZIndex>[0]) =>
  paneZIndex(a) > paneZIndex(b)

describe('zone pane stacking', () => {
  it('draws червоний over жовтий on their shared border', () => {
    // The whole reason these panes exist: two alerted neighbours share a border
    // line, and it must be painted by the more serious of the two — whichever
    // of them happened to light up last.
    expect(above(ZONE_OUTLINE_PANE.red, ZONE_OUTLINE_PANE.yellow)).toBe(true)
    expect(above(ZONE_GLOW_PANE.red, ZONE_GLOW_PANE.yellow)).toBe(true)
  })

  it('never lets a quiet raion cover a siren', () => {
    expect(above(ZONE_OUTLINE_PANE.yellow, ZONE_OUTLINE_PANE.clear)).toBe(true)
    expect(above(ZONE_OUTLINE_PANE.yellow, ZONE_OUTLINE_PANE.stale)).toBe(true)
  })

  it('keeps every glow under every outline', () => {
    expect(above(ZONE_OUTLINE_PANE.clear, ZONE_GLOW_PANE.red)).toBe(true)
    expect(above(ZONE_OUTLINE_PANE.clear, ZONE_ALL_CLEAR_PANE)).toBe(true)
    expect(above(ZONE_ALL_CLEAR_PANE, ZONE_GLOW_PANE.red)).toBe(true)
  })

  it('stays under the raion outlines it is background for', () => {
    // Between Leaflet's tilePane (200) and its overlayPane (400), where the
    // district and region boundaries live. Above the basemap, below everything
    // drawn on top of it — the placement MapView has always intended.
    for (const pane of [ZONE_GLOW_PANE.yellow, ZONE_OUTLINE_PANE.red]) {
      expect(paneZIndex(pane)).toBeGreaterThan(200)
      expect(paneZIndex(pane)).toBeLessThan(400)
    }
  })
})
