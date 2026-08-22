import type { StateCreator } from 'zustand'

import { fetchAlertZoneGeometry } from '@/api'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import { allClearedZoneIds } from '@/lib/zoneTransitions'
import type { AlertZone, AlertZoneGeometry } from '@/types'

import type { RadarState } from './types'

/** How long a raion stays lit green after its siren is called off.
 * 6s === the .zone-allclear animation in index.css. */
export const ALL_CLEAR_FLASH_MS = 6000

export interface ZonesSlice {
  /** Siren state per watched raion, keyed by zone_id. */
  zones: Record<string, AlertZone>
  /** Polygons, loaded lazily the first time the layer is switched on — ~76 KB
   * that most sessions never need. */
  zoneGeometry: AlertZoneGeometry
  zoneLayerOn: boolean
  /** Bumped every time the operator switches the layer ON, so the map can widen
   * to fit the lit raions (see controllers/ZoneAutoFit). A counter rather than a
   * boolean because the same request can be made again and again, and it must
   * fire each time; 0 means "never asked". Deliberately NOT bumped at boot: a
   * remembered switch is not a gesture, and the map owes it no move. */
  zoneFitToken: number
  /** Raions whose all-clear just landed, held for ALL_CLEAR_FLASH_MS so the map
   * can light them green. A moment, not a state — nothing reads it as "quiet". */
  zoneAllClear: Record<string, true>
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

// One expiry timer per flashing raion. The flash outlives no state of its own,
// so it has to be taken back on a clock rather than by the next frame — the
// provider is polled every 20 s and would leave a green raion sitting there.
const flashTimers = new Map<string, ReturnType<typeof setTimeout>>()

export const createZonesSlice: StateCreator<RadarState, [], [], ZonesSlice> = (set, get) => ({
  zones: {},
  zoneGeometry: {},
  zoneLayerOn: safeGet(STORAGE_KEYS.zoneLayer) === '1',
  zoneFitToken: 0,
  zoneAllClear: {},
  // Both the hydration fetch and the WS frame land here: a frame carries only
  // the zones that changed, so this merges rather than replaces.
  setZones: (zones) => {
    const cleared = allClearedZoneIds(get().zones, zones)
    set((s) => ({
      zones: { ...s.zones, ...byId(zones) },
      zoneAllClear: cleared.length
        ? { ...s.zoneAllClear, ...Object.fromEntries(cleared.map((id) => [id, true])) }
        : s.zoneAllClear,
    }))
    for (const zoneId of cleared) {
      clearTimeout(flashTimers.get(zoneId))
      flashTimers.set(
        zoneId,
        setTimeout(() => {
          flashTimers.delete(zoneId)
          set((s) => ({
            zoneAllClear: Object.fromEntries(
              Object.entries(s.zoneAllClear).filter(([id]) => id !== zoneId),
            ),
          }))
        }, ALL_CLEAR_FLASH_MS),
      )
    }
  },
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
    set((st) => ({ zoneLayerOn: on, zoneFitToken: on ? st.zoneFitToken + 1 : st.zoneFitToken }))
    if (on) get().ensureZoneGeometry()
  },
})
