import {
  fetchActiveAlerts,
  fetchActiveAxes,
  fetchActiveIncidents,
  fetchActiveThreats,
  fetchBoundaries,
  fetchDistricts,
  fetchHealth,
  fetchRecentEvents,
  fetchRecentIncidents,
  fetchRecentNotices,
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
export async function hydrate(): Promise<void> {
  const store = useRadar.getState()

  await Promise.all([
    fetchActiveThreats().then(store.setThreats).catch(() => {}),
    fetchActiveIncidents().then(store.setIncidents).catch(() => {}),
    fetchRecentIncidents().then(store.setRecentIncidents).catch(() => {}),
    fetchActiveAxes().then(store.setAxes).catch(() => {}),
    fetchActiveAlerts().then(store.setAlerts).catch(() => {}),
    fetchRecentEvents().then(store.setLog).catch(() => {}),
    fetchRecentNotices().then(store.setNotices).catch(() => {}),
    // Hydrate feed health once; live changes arrive via the WS 'health' frame.
    fetchHealth()
      .then((h) => store.setFeedOk(h.telegram?.feed_ok ?? null))
      .catch(() => {}),
  ])
}

/** One-shot static data + first hydration + live WS connection for the radar
 * app — never called for the changelog route, which needs none of this (see
 * main.tsx). */
export function bootstrapApp() {
  const store = useRadar.getState()

  fetchDistricts().then(store.setDistricts).catch(() => {})
  fetchBoundaries().then(store.setBoundaries).catch(() => {})

  hydrate()
  connectWS()
  registerLifecycleListeners()

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
