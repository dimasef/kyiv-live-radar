import { describe, expect, it } from 'vitest'

import { cardPlateHtml } from './cardPlate'
import { CARDS } from './cards'

const byRarity = (r: string) => CARDS.filter((c) => c.rarity === r).map((c) => c.id)

describe('cardPlateHtml — rare glyph tagging', () => {
  // The tag is applied by pattern-matching the plate markup, so a plate written
  // slightly differently would silently drop rare's only animation.
  it('tags the glyph on EVERY rare card', () => {
    const missed = byRarity('rare').filter(
      (id) => !cardPlateHtml(id, { animated: true, count: 1 }).includes('card-rare-glyph'),
    )
    expect(missed).toEqual([])
  })

  it('tags exactly one element per plate', () => {
    for (const id of byRarity('rare')) {
      const html = cardPlateHtml(id, { animated: true, count: 1 })
      expect(html.match(/card-rare-glyph/g)).toHaveLength(1)
    }
  })

  it('leaves other rarities alone', () => {
    for (const r of ['common', 'legendary', 'epic', 'eternal']) {
      for (const id of byRarity(r)) {
        expect(cardPlateHtml(id, { animated: true, count: 1 })).not.toContain('card-rare-glyph')
      }
    }
  })

  it('does not tag a still grid tile', () => {
    for (const id of byRarity('rare')) {
      expect(cardPlateHtml(id, { animated: false, count: 1 })).not.toContain('card-rare-glyph')
    }
  })
})

describe('cardPlateHtml — existing behaviour still holds', () => {
  it('freezes plate animations when not animated', () => {
    // The eternal card is the only plate with its own animations.
    const eternal = byRarity('eternal')[0]
    expect(cardPlateHtml(eternal, { animated: false, count: 1 })).not.toMatch(
      /animation:\s*card-/,
    )
    expect(cardPlateHtml(eternal, { animated: true, count: 1 })).toMatch(/animation:\s*card-/)
  })

  it('shows the duplicate badge only above one copy', () => {
    const id = CARDS[0].id
    expect(cardPlateHtml(id, { animated: false, count: 1 })).not.toContain('×')
    expect(cardPlateHtml(id, { animated: false, count: 3 })).toContain('×3')
  })
})
