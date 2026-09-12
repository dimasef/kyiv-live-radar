import type { TFunction } from 'i18next'

import {
  ACCOUNT_PATH,
  CHANGELOG_PATH,
  isAdminRoute,
  isCollectionRoute,
  isJournalRoute,
  journalTabFromPath,
  RESET_PASSWORD_PATH,
  userRouteId,
  VERIFY_EMAIL_PATH,
} from '@/router'

export const SITE_ORIGIN = 'https://www.ua-radar.online'

export interface DocumentMeta {
  title: string
  /** Whether a search engine may list this page. Everything behind a sign-in
   * or a role is not: the server gates it anyway, but a crawler that lands on
   * an empty shell would index the shell. */
  indexable: boolean
  /** The address a crawler should treat as THE one for this page. The site is
   * also served from its old vercel.app host (installed PWAs still live there),
   * so without this the two are duplicates. */
  canonical: string | null
}

export function documentMeta(path: string, t: TFunction): DocumentMeta {
  const app = t('app.title')
  const page = (name: string) => `${name} — ${app}`
  if (isJournalRoute(path)) {
    const tab = journalTabFromPath(path)
    const name = tab === 'stats' ? `${t('nav.journal')} · ${t('journal.tabs.stats')}` : t('nav.journal')
    return { title: page(name), indexable: true, canonical: `${SITE_ORIGIN}${path}` }
  }
  if (path === CHANGELOG_PATH) {
    return { title: page(t('changelog.title')), indexable: true, canonical: `${SITE_ORIGIN}${path}` }
  }
  if (isAdminRoute(path)) return { title: page(t('nav.admin')), indexable: false, canonical: null }
  if (path === ACCOUNT_PATH) return { title: page(t('nav.account')), indexable: false, canonical: null }
  if (path === VERIFY_EMAIL_PATH || path === RESET_PASSWORD_PATH) {
    return { title: page(t('nav.account')), indexable: false, canonical: null }
  }
  if (isCollectionRoute(path)) return { title: page(t('nav.collection')), indexable: false, canonical: null }
  if (userRouteId(path) != null) return { title: app, indexable: false, canonical: null }
  return { title: `${app} — ${t('meta.mapTitle')}`, indexable: true, canonical: `${SITE_ORIGIN}/` }
}

function headTag<K extends 'link' | 'meta'>(tag: K, selector: string, attrs: Record<string, string>) {
  let el = document.head.querySelector<HTMLElementTagNameMap[K]>(`${tag}${selector}`)
  if (!el) {
    el = document.createElement(tag)
    document.head.appendChild(el)
  }
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  return el
}

export function applyDocumentMeta(meta: DocumentMeta) {
  document.title = meta.title
  const canonical = document.head.querySelector('link[rel="canonical"]')
  if (meta.canonical) headTag('link', '[rel="canonical"]', { rel: 'canonical', href: meta.canonical })
  else canonical?.remove()
  const robots = document.head.querySelector('meta[name="robots"]')
  if (meta.indexable) robots?.remove()
  else headTag('meta', '[name="robots"]', { name: 'robots', content: 'noindex' })
}
