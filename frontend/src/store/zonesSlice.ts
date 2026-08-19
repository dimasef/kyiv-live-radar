import type { StateCreator } from 'zustand'

import { fetchAlertZoneGeometry } from '@/api'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import type { AlertZone, AlertZoneGeometry } from '@/types'

import type { RadarState } from './types'

export interface ZonesSlice {
  /** Siren state per watched raion, keyed by zone_id. */
  zones: Record<string, AlertZone>
  /** Polygons, loaded lazily the first time the layer is switched on — ~76 KB
   * that most sessions never need. */
  zoneGeometry: AlertZoneGeometry
  zoneLayerOn: boolean
  setZones: (zones: AlertZone[]) => void
  /** Load the polygons if the layer is on and doesn't have them yet. Called on
   * toggle-on AND at boot — the switch is remembered across reloads, so a
   * session that starts with it already on must fetch them too. No-op while
   * the layer is off, which is what keeps them lazy. */
  ensureZoneGeometry: () => void
  toggleZoneLayer: () => void
}

const byId = (zones: AlertZone[]): Record<string, AlertZone> =>
  Object.fromEntries(zones.map((z) => [z.zone_id, z]))

// In flight, so toggling the layer off and on again doesn't stack fetches.
let geometryPending = false

export const createZonesSlice: StateCreator<RadarState, [], [], ZonesSlice> = (set, get) => ({
  zones: {},
  zoneGeometry: {},
  zoneLayerOn: safeGet(STORAGE_KEYS.zoneLayer) === '1',
  // Both the hydration fetch and the WS frame land here: a frame carries only
  // the zones that changed, so this merges rather than replaces.
  setZones: (zones) => set((s) => ({ zones: { ...s.zones, ...byId(zones) } })),
  ensureZoneGeometry: () => {
    const s = get()
    // Still lazy: a session that never turns the layer on never pays the 76 KB.
    if (!s.zoneLayerOn || geometryPending || Object.keys(s.zoneGeometry).length > 0) return
    geometryPending = true
    fetchAlertZoneGeometry()
      .then((geometry) => set({ zoneGeometry: geometry }))
      .catch(() => {})
      .finally(() => {
        geometryPending = false
      })
  },
  toggleZoneLayer: () => {
    const on = !get().zoneLayerOn
    safeSet(STORAGE_KEYS.zoneLayer, on ? '1' : '0')
    set({ zoneLayerOn: on })
    if (on) get().ensureZoneGeometry()
  },
})
