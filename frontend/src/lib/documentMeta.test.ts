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

  it('keeps everything behind a sign-in or a role out of the index', () => {
    for (const path of ['/admin', '/admin/raw', '/raw', '/account', '/collection', '/collection/7', '/user/3']) {
      const m = documentMeta(path, t)
      expect(m.indexable, path).toBe(false)
      expect(m.canonical, path).toBeNull()
    }
  })
})
