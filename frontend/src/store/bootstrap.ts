import {
  fetchRecentAlerts,
  fetchActiveAxes,
  fetchActiveIncidents,
  fetchActiveThreats,
  fetchAlertZones,
  fetchBoundaries,
  fetchDistricts,
  fetchHealth,
  fetchRecentEvents,
  fetchRecentIncidents,
  fetchRecentNotices,
  fetchPublicSources,
} from '@/api'
import { requestGeolocation } from '@/components/chrome'
import { resyncHomePush } from '@/lib/push'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import { registerLifecycleListeners } from '@/lifecycle'
import { connectWS } from '@/ws'

import { useRadar } from './index'

/** Re-fetches every active/recent data set (everything EXCEPT the
 * once-per-session static ones — districts/boundaries). Re-runnable: this is
 * the safety net for a stale slice missed while the WS was dead — each
 * `setX` REPLACES its slice from the server's current active set, so
 * anything closed/cleared while we were disconnected drops out on its own.
 * Called both by bootstrap and by `ws.ts`'s resync-on-reconnect. */
/** When the last full hydrate finished — resync()'s freshness guard reads it
 * to skip a redundant refetch right after boot (live `let` export binding). */
export let lastHydrateAt = 0

let latestHydrate = 0
let inFlight: { promise: Promise<void>; startedAt: number } | null = null
// Two hydrates fired within this window are the same intent, not two.
const HYDRATE_COALESCE_MS = 2_000

export function hydrate(): Promise<void> {
  // Boot and reconnect each want a full reconcile and fire milliseconds apart —
  // `bootstrapApp` hydrates, then `connectWS`'s onopen hydrates again; a resync
  // does the same via forceReconnect. Join the run already going rather than
  // doubling all ten requests. Past the window the in-flight one may simply be
  // hung on a dead network — which is exactly when a resume needs fresh
  // requests — so let it start a new one and rely on the generation guard.
  if (inFlight && Date.now() - inFlight.startedAt < HYDRATE_COALESCE_MS) return inFlight.promise

  const promise = runHydrate().finally(() => {
    if (inFlight?.promise === promise) inFlight = null
  })
  inFlight = { promise, startedAt: Date.now() }
  return promise
}

async function runHydrate(): Promise<void> {
  const generation = ++latestHydrate
  const store = useRadar.getState()
  const isCurrent = () => generation === latestHydrate

  // A slower older hydrate landing after a newer one must not repaint the map
  // from its stale snapshot — a target that closed in between would come back.
  let anySucceeded = false
  const apply =
    <T>(set: (value: T) => void) =>
    (value: T) => {
      anySucceeded = true
      if (isCurrent()) set(value)
    }

  await Promise.all([
    fetchActiveThreats().then(apply(store.setThreats)).catch(() => {}),
    fetchActiveIncidents().then(apply(store.setIncidents)).catch(() => {}),
    fetchRecentIncidents().then(apply(store.setRecentIncidents)).catch(() => {}),
    fetchActiveAxes().then(apply(store.setAxes)).catch(() => {}),
    fetchRecentAlerts().then(apply(store.setAlerts)).catch(() => {}),
    fetchAlertZones().then(apply(store.setZones)).catch(() => {}),
    fetchRecentEvents(store.feedLimit, store.feedOtherRegions ? undefined : 'kyiv')
      .then(apply(store.setLog))
      .catch(() => {}),
    fetchRecentNotices().then(apply(store.setNotices)).catch(() => {}),
    fetchPublicSources().then(apply(store.setSources)).catch(() => {}),
    // Hydrate feed health once; live changes arrive via the WS 'health' frame.
    // `server_time` seeds the fade clock's skew correction before the first ping.
    fetchHealth()
      .then(
        apply((h: Awaited<ReturnType<typeof fetchHealth>>) => {
          store.setFeedOk(h.telegram?.feed_ok ?? null)
          store.setServerTime(h.server_time)
        }),
      )
      .catch(() => {}),
  ])

  // Stamping this when EVERY request failed would make resync()'s freshness
  // guard skip the recovery refetch for the next 10s — precisely when the
  // backend is coming back and we most need to re-ask.
  if (isCurrent() && anySucceeded) lastHydrateAt = Date.now()
}

/** One-shot static data + first hydration + live WS connection for the radar
 * app — never called for the changelog route, which needs none of this (see
 * main.tsx). Guarded to run a single time per app session: the map route
 * (App.tsx) remounts on every in-app navigation back to Мапа, and re-running
 * this would stack duplicate WS connections + lifecycle listeners and refire a
 * full refetch. After the first boot the live WS (+ its resync-on-reconnect)
 * keeps every slice fresh, so a remount needs no re-bootstrap. */
let bootstrapped = false

export function bootstrapApp() {
  if (bootstrapped) return
  bootstrapped = true

  const store = useRadar.getState()

  fetchDistricts().then(store.setDistricts).catch(() => {})
  fetchBoundaries().then(store.setBoundaries).catch(() => {})
  // The alert-layer switch survives reloads, so a session can start with it
  // already on — its polygons are lazy, and without this the button would light
  // up with nothing drawn. No-op when the layer is off.
  store.ensureZoneGeometry()

  hydrate()
  connectWS()
  registerLifecycleListeners()
  // Drives the map's staleness fade — one timer for the whole app, paused while
  // the tab is hidden (see clockSlice).
  store.startClock()

  // Poll the friend graph while signed in and foregrounded — friend requests /
  // acceptances have no live WS channel, so this is what surfaces an incoming
  // request (or a contact who just accepted) without a page reload. Resume
  // events (lifecycle.ts) refresh on top of this when the tab regains focus.
  setInterval(() => {
    const s = useRadar.getState()
    if (s.authStatus === 'authed' && document.visibilityState === 'visible') {
      void s.loadFriends().catch(() => {})
    }
  }, 30_000)

  // Ask for the user's real location once, on the very first run — NOT every
  // time home is missing. Otherwise clearing home and reloading would silently
  // re-set it from an already-granted geolocation permission. The marker is
  // stamped on the first boot regardless of whether a home already exists, so a
  // later clear never re-triggers the prompt; the manual "use my location"
  // button stays available afterwards.
  const firstRun = !safeGet(STORAGE_KEYS.geoAsked)
  if (firstRun) safeSet(STORAGE_KEYS.geoAsked, '1')
  if (firstRun && !store.home) requestGeolocation()

  // Notifications opted in: re-register the still-live browser subscription so
  // the server's home copy heals from anything missed offline (home edited in
  // another tab, a wiped backend DB, ...).
  if (store.notifyStatus === 'on') void resyncHomePush(store.home, store.notifyPrefs).catch(() => {})
}
