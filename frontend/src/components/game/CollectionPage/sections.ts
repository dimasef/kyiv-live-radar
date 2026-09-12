import { RARITIES, type Rarity } from '@/lib/cards'

export const sectionId = (rarity: Rarity) => `rarity-${rarity}`

export const SECTION_IDS = RARITIES.map(sectionId)

export function rarityOfSection(id: string | null): Rarity | null {
  return RARITIES.find((r) => sectionId(r) === id) ?? null
}

/** «1 копія», «3 копії», «5 копій», «11 копій» — Ukrainian plural forms. */
export function copiesLabel(n: number): string {
  const tens = n % 100
  const ones = n % 10
  const word =
    tens >= 11 && tens <= 14 ? 'копій' : ones === 1 ? 'копія' : ones >= 2 && ones <= 4 ? 'копії' : 'копій'
  return `${n} ${word}`
}
