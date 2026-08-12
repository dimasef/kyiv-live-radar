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
export const ADMIN_TABS = ['manage', 'bugs', 'sources', 'gaps', 'corrections', 'reprocess', 'raw'] as const
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

// Collectible-card collection. `/collection` shows your own; `/collection/<id>`
// shows a friend's (server gates it to accepted friends).
export const COLLECTION_PATH = '/collection'

/** True for the collection route (own or a friend's). */
export function isCollectionRoute(path: string): boolean {
  return path === COLLECTION_PATH || path.startsWith(`${COLLECTION_PATH}/`)
}

/** The friend user id in `/collection/<id>`, or null for your own collection. */
export function collectionUserId(path: string): number | null {
  if (!path.startsWith(`${COLLECTION_PATH}/`)) return null
  const id = Number(path.slice(COLLECTION_PATH.length + 1))
  return Number.isInteger(id) && id > 0 ? id : null
}

/** URL for a user's collection ('own' = your own). */
export function collectionPath(userId?: number): string {
  return userId ? `${COLLECTION_PATH}/${userId}` : COLLECTION_PATH
}

// A contact's profile page — who they are, their collection, who they know.
// Everything on it is server-gated to that person's accepted contacts, so the
// route only ever resolves to content for someone you're actually connected to.
export const USER_PATH = '/user'

/** The user id in `/user/<id>`, or null when the path isn't a user route. */
export function userRouteId(path: string): number | null {
  if (!path.startsWith(`${USER_PATH}/`)) return null
  const id = Number(path.slice(USER_PATH.length + 1))
  return Number.isInteger(id) && id > 0 ? id : null
}

/** URL for one user's profile page. */
export function userPath(userId: number): string {
  return `${USER_PATH}/${userId}`
}
