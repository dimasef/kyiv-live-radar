import { describe, expect, it } from 'vitest'

import { CARDS, RARITIES } from './cards'
import { CARD_PLATES } from './cardGlyphs'

describe('the card catalog', () => {
  it('has a unique id per card, with none missing between 1 and the last', () => {
    // The id is what the DATABASE stores (threat_analyses.card_id), so a
    // duplicate would hand two different cards to the same row and a gap would
    // make the backend's CARD_COUNT range draw a card that does not exist.
    const ids = CARDS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect([...ids].sort((a, b) => a - b)).toEqual(
      Array.from({ length: CARDS.length }, (_, i) => i + 1),
    )
  })

  it('has a plate for every card', () => {
    // A card with no plate renders an empty frame — visible only if someone
    // happens to draw that exact id, which for a rare one can take weeks.
    const missing = CARDS.filter((c) => !CARD_PLATES[c.id])
    expect(missing.map((c) => `${c.id} ${c.title}`)).toEqual([])
  })

  it('ships no canvas-mangled attributes in a plate', () => {
    // The design canvas spells camelCase SVG attributes `sc-camel-view-box`;
    // left in, the browser ignores them and the glyph renders at the wrong
    // scale or not at all.
    const bad = Object.entries(CARD_PLATES).filter(([, html]) => html.includes('sc-camel-'))
    expect(bad.map(([id]) => id)).toEqual([])
  })

  it('groups cards by ascending rarity, which is how the collection lays them out', () => {
    const seen = CARDS.map((c) => RARITIES.indexOf(c.rarity))
    expect(seen).toEqual([...seen].sort((a, b) => a - b))
  })
})
