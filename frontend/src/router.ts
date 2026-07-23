import { useEffect, useState } from 'react'

/** SPA navigation without a router library — pushes history and notifies the
 * useRoute() subscribers. */
export function navigate(to: string) {
  if (window.location.pathname === to) return
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** Current pathname, re-rendering on back/forward and navigate(). */
export function useRoute(): string {
  const [path, setPath] = useState(() => window.location.pathname)
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  return path
}

// The radar map — the app's default/home route.
export const MAP_PATH = '/'
export const CHANGELOG_PATH = '/change-log'
// Operator-facing calendar of past aerial-threat activity (linked from Settings).
export const THREAT_JOURNAL_PATH = '/journal'
// Hidden debug route (not linked from the UI) — every raw ingested message,
// including ones the parser suppressed or couldn't localize. See /raw.
// Now admin-only: the backend 403s a non-admin (see components/raw).
export const RAW_MESSAGES_PATH = '/raw'
// Signed-in user's account page (profile, linked providers, sign-out).
export const ACCOUNT_PATH = '/account'
