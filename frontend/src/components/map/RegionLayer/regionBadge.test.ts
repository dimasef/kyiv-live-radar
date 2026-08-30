import { describe, expect, it } from 'vitest'

import { badgeLabel, badgeStateOf } from './regionBadge'

describe('badgeStateOf', () => {
  it('reads the followed region as followed, whatever the feed says', () => {
    // The followed region is always in the feed and has no "off" — so `inFeed`
    // carries no information for it, and letting it win would render the one
    // state the reader CANNOT toggle as a toggle.
    expect(badgeStateOf({ isHome: true, inFeed: true })).toBe('followed')
    expect(badgeStateOf({ isHome: true, inFeed: false })).toBe('followed')
  })

  it('separates an added region from an untouched one', () => {
    expect(badgeStateOf({ isHome: false, inFeed: true })).toBe('inFeed')
    expect(badgeStateOf({ isHome: false, inFeed: false })).toBe('out')
  })
})

describe('badgeLabel', () => {
  it('gives every state its own words for a screen reader', () => {
    const labels = (['followed', 'inFeed', 'out'] as const).map(badgeLabel)
    expect(new Set(labels).size).toBe(3)
    for (const label of labels) expect(label.length).toBeGreaterThan(0)
  })
})
