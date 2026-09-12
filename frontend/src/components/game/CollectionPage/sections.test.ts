import { describe, expect, it } from 'vitest'

import { copiesLabel, rarityOfSection, sectionId } from './sections'

describe('copiesLabel', () => {
  it('declines the noun by the count', () => {
    expect(copiesLabel(0)).toBe('0 копій')
    expect(copiesLabel(1)).toBe('1 копія')
    expect(copiesLabel(3)).toBe('3 копії')
    expect(copiesLabel(5)).toBe('5 копій')
    expect(copiesLabel(11)).toBe('11 копій')
    expect(copiesLabel(14)).toBe('14 копій')
    expect(copiesLabel(21)).toBe('21 копія')
    expect(copiesLabel(112)).toBe('112 копій')
    expect(copiesLabel(122)).toBe('122 копії')
  })
})

describe('rarityOfSection', () => {
  it('round-trips a section id and rejects anything else', () => {
    expect(rarityOfSection(sectionId('epic'))).toBe('epic')
    expect(rarityOfSection('rarity-nope')).toBeNull()
    expect(rarityOfSection(null)).toBeNull()
  })
})
