import { describe, expect, it } from 'vitest'

import { journalDateFromPath, journalDayPath, journalTabFromPath, isJournalRoute } from './router'

describe('journalDateFromPath', () => {
  it('reads the day a journal URL names', () => {
    expect(journalDateFromPath('/journal/2026-09-14')).toBe('2026-09-14')
  })

  it('has no day for the calendar and statistics routes', () => {
    expect(journalDateFromPath('/journal')).toBeNull()
    expect(journalDateFromPath('/journal/stats')).toBeNull()
    expect(journalDateFromPath('/')).toBeNull()
  })

  it('refuses a date that is not a real day', () => {
    // Four numbers in the right shape, but no such date — rolling it over to
    // 3 March would publish an address that answers with a different day than
    // it spells.
    expect(journalDateFromPath('/journal/2026-02-31')).toBeNull()
    expect(journalDateFromPath('/journal/2026-13-01')).toBeNull()
    expect(journalDateFromPath('/journal/2026-9-14')).toBeNull()
    expect(journalDateFromPath('/journal/not-a-date')).toBeNull()
  })

  it('keeps a leap day, which is a real one', () => {
    expect(journalDateFromPath('/journal/2028-02-29')).toBe('2028-02-29')
    expect(journalDateFromPath('/journal/2027-02-29')).toBeNull()
  })

  it('round-trips through journalDayPath', () => {
    expect(journalDateFromPath(journalDayPath('2026-07-18'))).toBe('2026-07-18')
  })
})

describe('a day route is still a calendar route', () => {
  it('so the tabs stay lit and the page renders the calendar', () => {
    expect(isJournalRoute('/journal/2026-09-14')).toBe(true)
    expect(journalTabFromPath('/journal/2026-09-14')).toBe('calendar')
  })
})
