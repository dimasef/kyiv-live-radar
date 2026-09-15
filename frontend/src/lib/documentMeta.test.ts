import { describe, expect, it } from 'vitest'

import type { TFunction } from 'i18next'

import { documentMeta, SITE_ORIGIN } from './documentMeta'

const t = ((key: string) => key) as unknown as TFunction

describe('documentMeta', () => {
  it('names the map after the app and makes it canonical at the root', () => {
    const m = documentMeta('/', t)
    expect(m).toEqual({ title: 'app.title — meta.mapTitle', indexable: true, canonical: `${SITE_ORIGIN}/` })
  })

  it('indexes the journal tabs and the changelog under their own canonical', () => {
    expect(documentMeta('/journal/stats', t)).toMatchObject({
      title: 'nav.journal · journal.tabs.stats — app.title',
      indexable: true,
      canonical: `${SITE_ORIGIN}/journal/stats`,
    })
    expect(documentMeta('/change-log', t).canonical).toBe(`${SITE_ORIGIN}/change-log`)
  })

  it('gives a journal day its own title and canonical', () => {
    // The date leads, because «Журнал» is the same word on every one of these
    // and the date is what tells two search results apart.
    expect(documentMeta('/journal/2026-09-14', t)).toEqual({
      title: '14 вересня 2026 · nav.journal — app.title',
      indexable: true,
      canonical: `${SITE_ORIGIN}/journal/2026-09-14`,
    })
  })

  it('points every junk journal sub-path back at the calendar', () => {
    // They all RENDER the calendar, so each one declaring itself a page of its
    // own is an unbounded supply of duplicates — and /journal/2026-02-31 would
    // additionally be an address that answers with a different date than it
    // spells.
    for (const path of ['/journal/2026-02-31', '/journal/anything', '/journal/2026-9-14']) {
      expect(documentMeta(path, t), path).toEqual({
        title: 'nav.journal — app.title',
        indexable: true,
        canonical: `${SITE_ORIGIN}/journal`,
      })
    }
  })

  it('keeps everything behind a sign-in or a role out of the index', () => {
    for (const path of ['/admin', '/admin/raw', '/raw', '/account', '/collection', '/collection/7', '/user/3']) {
      const m = documentMeta(path, t)
      expect(m.indexable, path).toBe(false)
      expect(m.canonical, path).toBeNull()
    }
  })
})
