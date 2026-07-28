import { useRadar } from './store'
import { resync } from './ws'

let registered = false

/** Ties WS recovery to page/network events the store can't otherwise observe.
 * A backgrounded/frozen tab's socket can die silently with no `close` event,
 * so resuming (tab visible again, refocused, restored from bfcache, network
 * back) is the primary recovery trigger for that case — the watchdog in
 * ws.ts only covers a zombie socket while the tab stays foreground. */
export function registerLifecycleListeners() {
  if (registered) return
  registered = true

  const onResume = () => {
    resync()
    // Friend requests/acceptances have no live WS channel — refresh them when
    // the user returns so an incoming request or a just-accepted contact shows
    // up without a manual reload (awkward in the installed PWA).
    const s = useRadar.getState()
    if (s.authStatus === 'authed') void s.loadFriends().catch(() => {})
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') onResume()
  })
  window.addEventListener('focus', onResume)
  // `pageshow` fires on EVERY navigation, not just bfcache restores — an
  // unguarded listener re-hydrated the whole app seconds after bootstrap
  // already had. Only the restored-from-bfcache case is a real resume.
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) onResume()
  })
  window.addEventListener('online', onResume)
  window.addEventListener('offline', () => useRadar.getState().setConnected(false))
}
