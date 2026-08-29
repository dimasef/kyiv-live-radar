import { describe, expect, it } from 'vitest'

import type { RegionInfo } from '@/types'

import { foreignJournalRegion } from './journalRegion'

const catalogue = [
  { id: 'kyiv', name_uk: 'Київщина', is_home: true, active: true },
  { id: 'sumy', name_uk: 'Сумщина', is_home: false, active: true },
] as unknown as RegionInfo[]

describe('whose journal a reader is actually looking at', () => {
  it('names the home region for someone following another oblast', () => {
    // The journal is aggregated server-side over the home region alone, and
    // nothing on the page said so — a heat map of Kyiv raions reads as "my
    // area" to a Сумщина reader.
    expect(foreignJournalRegion(catalogue, 'sumy')).toBe('Київщина')
  })

  it('stays out of the way for a reader in the home region', () => {
    expect(foreignJournalRegion(catalogue, 'kyiv')).toBeNull()
  })

  it('stays out of the way before the picker is answered', () => {
    // No choice yet falls back to home, so the journal IS about them.
    expect(foreignJournalRegion(catalogue, null)).toBeNull()
  })

  it('does not gate the page on a catalogue that has not loaded', () => {
    // No home region known means no name to show and no comparison to make;
    // blocking the page on data still in flight would be worse than showing it.
    expect(foreignJournalRegion([], 'sumy')).toBeNull()
  })
})
