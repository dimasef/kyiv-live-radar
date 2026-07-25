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
// Admin console (replaces the standalone /raw tab in the header). Hosts the
// manual parser-override controls plus the raw-message log as tabs. Admin-only:
// the page gates on role and every /admin/* backend endpoint 403s non-admins.
export const ADMIN_PATH = '/admin'
// Raw ingested-message log — every message, including ones the parser suppressed
// or couldn't localize. Now lives inside the admin console as a tab; this path
// still resolves there (opens the log tab) for existing bookmarks/exports.
export const RAW_MESSAGES_PATH = '/raw'
// Signed-in user's account page (profile, linked providers, sign-out).
export const ACCOUNT_PATH = '/account'
