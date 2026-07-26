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

// Admin console tabs, each its own route (/admin/<tab>) so a reload keeps the
// open tab instead of snapping back to the first one. 'manage' is the bare
// /admin route; 'raw' also answers the legacy /raw path (see adminTabFromPath).
export const ADMIN_TABS = ['manage', 'sources', 'gaps', 'corrections', 'reprocess', 'raw'] as const
export type AdminTab = (typeof ADMIN_TABS)[number]

/** True for any admin route: /admin, /admin/<tab>, or the legacy /raw. */
export function isAdminRoute(path: string): boolean {
  return path === ADMIN_PATH || path.startsWith(`${ADMIN_PATH}/`) || path === RAW_MESSAGES_PATH
}

/** The URL for a given admin tab. 'manage' is the bare /admin. */
export function adminTabPath(tab: AdminTab): string {
  return tab === 'manage' ? ADMIN_PATH : `${ADMIN_PATH}/${tab}`
}

/** The admin tab a path selects; unknown sub-paths fall back to 'manage'. */
export function adminTabFromPath(path: string): AdminTab {
  if (path === RAW_MESSAGES_PATH) return 'raw'
  if (path === ADMIN_PATH) return 'manage'
  const seg = path.slice(ADMIN_PATH.length + 1)
  return (ADMIN_TABS as readonly string[]).includes(seg) ? (seg as AdminTab) : 'manage'
}
// Signed-in user's account page (profile, linked providers, sign-out).
export const ACCOUNT_PATH = '/account'
