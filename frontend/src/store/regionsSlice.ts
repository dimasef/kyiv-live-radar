import type { StateCreator } from 'zustand'

import { fetchRecentEvents, fetchRegionOutlines, fetchRegions } from '@/api'
import { resyncHomePush } from '@/lib/push'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'
import type { Region, RegionInfo, RegionOutlines } from '@/types'

import { pruneFeedRegions, shownRegions } from './feedRegions'
import type { RadarState } from './types'

export interface RegionsSlice {
  /** The watched-region catalogue, server-owned so a newly declared region
   * reaches the picker, the source grouping and the map with no code change
   * here. Empty until the boot fetch lands — every consumer has to tolerate
   * that, which is why nothing derives a hardcoded fallback list from it. */
  regions: RegionInfo[]
  /** Oblast outlines, loaded lazily the first time the map zooms out far enough
   * to draw them — the same deal the raion polygons get in zonesSlice. */
  regionOutlines: RegionOutlines
  setRegions: (regions: RegionInfo[]) => void
  /** Fetch the catalogue if it isn't here yet. Called from boot AND from the
   * admin page, which can be opened on a route that never bootstraps the map. */
  ensureRegions: () => void
  ensureRegionOutlines: () => void
  /** The region the reader chose — asked once on first run, changeable in
   * settings. It decides which region's tracks reach the feed and which ones
   * may notify; WHERE inside it the alerts fire is the separate home location.
   * Null until picked, which is what raises the first-run picker. */
  chosenRegion: Region | null
  setChosenRegion: (id: Region) => void
  /** Whether the "oblasts are clickable" hint is on screen right now. */
  regionHintVisible: boolean
  /** Called when the map first crosses into the oblast layer's zoom band.
   * Raises the hint once ever — the map opens fitted to the city, so nothing
   * else would bring a reader to a layer they have never seen. */
  noteRegionLayerSeen: () => void
}

/** How long the hint holds the top-centre stack. Same span ZONE_NOTICE_MS uses:
 * long enough to read, short enough not to become furniture. */
const HINT_MS = 5000

// In flight, so a page that mounts two consumers doesn't stack fetches.
function initialChosenRegion(): Region | null {
  return (safeGet(STORAGE_KEYS.region) as Region | null) || null
}

let regionsPending = false
let outlinesPending = false
let hintTimer: ReturnType<typeof setTimeout> | undefined

export const createRegionsSlice: StateCreator<RadarState, [], [], RegionsSlice> = (set, get) => ({
  regions: [],
  regionOutlines: {},
  chosenRegion: initialChosenRegion(),
  setChosenRegion: (id) => {
    safeSet(STORAGE_KEYS.region, id)
    set({ chosenRegion: id })
    // The feed page was fetched for the old region, and the server's copy of
    // this device still says the old one — both have to be told.
    const s = get()
    fetchRecentEvents(s.feedLimit, shownRegions(s.feedExtraRegions, id))
      .then(s.setLog)
      .catch(() => {})
    if (s.notifyStatus === 'on') void resyncHomePush(s.home, s.notifyPrefs, id).catch(() => {})
  },
  regionHintVisible: false,
  noteRegionLayerSeen: () => {
    if (safeGet(STORAGE_KEYS.regionHint) === '1' || get().regionHintVisible) return
    safeSet(STORAGE_KEYS.regionHint, '1')
    set({ regionHintVisible: true })
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => set({ regionHintVisible: false }), HINT_MS)
  },
  setRegions: (regions) => {
    // The catalogue arriving is the first chance to notice that a remembered
    // feed choice names a region the server no longer declares. One stale id
    // 422s the whole /events/recent page, and bootstrap's `.catch(() => {})`
    // turns that into a silently empty feed with nothing to say why.
    const extra = pruneFeedRegions(get().feedExtraRegions, regions)
    if (extra.length !== get().feedExtraRegions.length) {
      safeSet(STORAGE_KEYS.feedRegions, JSON.stringify(extra))
      set({ feedExtraRegions: extra })
    }
    set({ regions })
  },
  ensureRegions: () => {
    if (regionsPending || get().regions.length > 0) return
    regionsPending = true
    fetchRegions()
      .then((regions) => get().setRegions(regions))
      .catch(() => {})
      .finally(() => {
        regionsPending = false
      })
  },
  ensureRegionOutlines: () => {
    if (outlinesPending || Object.keys(get().regionOutlines).length > 0) return
    outlinesPending = true
    fetchRegionOutlines()
      .then((regionOutlines) => set({ regionOutlines }))
      .catch(() => {})
      .finally(() => {
        outlinesPending = false
      })
  },
})
