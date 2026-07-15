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

export const CHANGELOG_PATH = '/change-log'
// Hidden debug route (not linked from the UI) — every raw ingested message,
// including ones the parser suppressed or couldn't localize. See /raw.
export const RAW_MESSAGES_PATH = '/raw'
