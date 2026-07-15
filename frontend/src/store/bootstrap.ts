import {
  fetchActiveAlerts,
  fetchActiveIncidents,
  fetchActiveThreats,
  fetchBoundaries,
  fetchDistricts,
  fetchHealth,
  fetchRecentEvents,
  fetchRecentNotices,
} from '@/api'
import { requestGeolocation } from '@/components/chrome'
import { connectWS } from '@/ws'

import { useRadar } from './index'

/** One-shot data hydration + live WS connection for the radar app — never
 * called for the changelog route, which needs none of this (see main.tsx). */
export function bootstrapApp() {
  const store = useRadar.getState()

  fetchDistricts().then(store.setDistricts).catch(() => {})
  fetchBoundaries().then(store.setBoundaries).catch(() => {})
  fetchActiveThreats().then(store.setThreats).catch(() => {})
  fetchActiveIncidents().then(store.setIncidents).catch(() => {})
  fetchActiveAlerts().then(store.setAlerts).catch(() => {})
  fetchRecentEvents().then(store.setLog).catch(() => {})
  fetchRecentNotices().then(store.setNotices).catch(() => {})
  // Hydrate feed health once; live changes arrive via the WS 'health' frame.
  fetchHealth()
    .then((h) => store.setFeedOk(h.telegram?.feed_ok ?? null))
    .catch(() => {})

  connectWS()

  // Ask for the user's real location on first run (no saved home yet).
  if (!store.home) requestGeolocation()
}
