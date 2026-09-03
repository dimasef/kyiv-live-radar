import type { StateCreator } from 'zustand'

import { fetchRecentEvents, setGamificationPref } from '@/api'
import { currentRegion } from '@/lib/regions'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'
import type { Region } from '@/types'

import { migrateFeedRegions, shownRegions } from './feedRegions'
import type { RadarState } from './types'

/** How far the mobile bottom sheet (event feed) opens — 'low' peeks a short
 * list, 'high' fills most of the screen. Mobile-only; ignored on desktop. */
export type SheetHeight = 'low' | 'mid' | 'high'

const SHEET_HEIGHTS: SheetHeight[] = ['low', 'mid', 'high']

function initialSheetHeight(): SheetHeight {
  const saved = safeGet(STORAGE_KEYS.sheetHeight)
  return SHEET_HEIGHTS.includes(saved as SheetHeight) ? (saved as SheetHeight) : 'mid'
}

/** Event-feed text scale. Applied as CSS zoom on the feed list, so cards and
 * spacing scale together — not just the letterforms. */
export type FeedTextSize = 'sm' | 'md' | 'lg'

const FEED_TEXT_SIZES: FeedTextSize[] = ['sm', 'md', 'lg']

export const FEED_ZOOM: Record<FeedTextSize, number> = { sm: 0.85, md: 1, lg: 1.15 }

function initialFeedTextSize(): FeedTextSize {
  const saved = safeGet(STORAGE_KEYS.feedTextSize)
  return FEED_TEXT_SIZES.includes(saved as FeedTextSize) ? (saved as FeedTextSize) : 'md'
}

/** How many recent feed messages to fetch and keep. */
export const FEED_LIMITS = [30, 60, 120, 250] as const
export type FeedLimit = (typeof FEED_LIMITS)[number]

function initialFeedLimit(): FeedLimit {
  const saved = Number(safeGet(STORAGE_KEYS.feedLimit))
  return (FEED_LIMITS as readonly number[]).includes(saved) ? (saved as FeedLimit) : 60
}

/** Which non-home regions the feed lists. Defaults to every region that existed
 * when the old boolean was the setting — the reader has been seeing them, and a
 * filter that hides data by default is a filter nobody knows is there. A region
 * declared since then starts off, and the map's oblast menu is how it is found.
 * Affects the FEED ONLY; the map is a separate question. */
function initialFeedExtraRegions(): Region[] {
  const extra = migrateFeedRegions(
    safeGet(STORAGE_KEYS.feedRegions),
    safeGet(STORAGE_KEYS.feedOtherRegions),
  )
  safeSet(STORAGE_KEYS.feedRegions, JSON.stringify(extra))
  safeRemove(STORAGE_KEYS.feedOtherRegions)
  return extra
}

/** Whether a feed card names the channel the message came from. Defaults to on:
 * with several spotter channels of unequal reliability in one timeline, who said
 * it is part of how much to believe it — the map popup has always named the
 * source, and the feed was the one place that dropped it. Off is for when the
 * feed is scrolling too fast to want a second line per card. */
function initialFeedShowSource(): boolean {
  return safeGet(STORAGE_KEYS.feedShowSource) !== '0'
}

/** Whether the map draws the trail behind a target at all — the line and the
 * waypoint dots both.
 *
 * Off is a real reading of the map, not a degraded one: during a mass raid a
 * hundred crossing trails are noise, and "where are they" is a different
 * question from "where have they been". It only quietens the map AT REST —
 * ThreatLayer still draws the trail of whichever target is being inspected or
 * has its popup open, because asking about one target is the moment its path
 * becomes the answer. */
function initialMapTrail(): boolean {
  return safeGet(STORAGE_KEYS.mapTrail) !== '0'
}

/** Stroke width of that trail in px, once it is drawn. A plain number rather
 * than a thin/normal/thick enum: the reader is choosing a LOOK, and three
 * names for it were both fewer choices and less clear than the thing itself —
 * the slider shows the line it is setting. 3 is what the map always drew. */
export const TRACK_WIDTH_MIN = 1
export const TRACK_WIDTH_MAX = 8

function initialMapTrackWidth(): number {
  const saved = Number(safeGet(STORAGE_KEYS.mapTrackWidth))
  return Number.isInteger(saved) && saved >= TRACK_WIDTH_MIN && saved <= TRACK_WIDTH_MAX
    ? saved
    : 3
}

/** Target marker size in px. `md` is the size the map has always drawn. */
export type MapMarkerSize = 'sm' | 'md' | 'lg'

const MAP_MARKER_SIZES: MapMarkerSize[] = ['sm', 'md', 'lg']

export const MARKER_PX: Record<MapMarkerSize, number> = { sm: 20, md: 26, lg: 34 }

function initialMapMarkerSize(): MapMarkerSize {
  const saved = safeGet(STORAGE_KEYS.mapMarkerSize)
  return MAP_MARKER_SIZES.includes(saved as MapMarkerSize) ? (saved as MapMarkerSize) : 'md'
}

/** Whether the map animates at all — pulsing heads, the crawling dash along a
 * live track, the drift of a marker between reports. Defaults ON, because that
 * motion is what tells a live target from a stale one at a glance. Turning it
 * off keeps every SHAPE and every colour: a live track still reads as dashed,
 * it just stops moving. For weak devices, the TV browser, and anyone who does
 * not want a moving map (see MOTION_BUDGET, which does the same thing
 * automatically once the map gets crowded). */
function initialMapMotion(): boolean {
  return safeGet(STORAGE_KEYS.mapMotion) !== '0'
}

export interface PrefsSlice {
  sheetHeight: SheetHeight
  setSheetHeight: (h: SheetHeight) => void
  feedTextSize: FeedTextSize
  setFeedTextSize: (s: FeedTextSize) => void
  feedLimit: FeedLimit
  setFeedLimit: (n: FeedLimit) => void
  /** Watched regions OTHER than home whose sightings the feed lists. The home
   * region is deliberately absent and can never be turned off — `shownRegions`
   * adds it back, so no stored state can exist without it. The map ignores this.
   *
   * An explicit set rather than an "everything" mode: with several approach
   * regions, "all" stops being a sensible default — someone who opted into
   * Чернігівщина has not asked for a newly added one to appear in their feed. */
  feedExtraRegions: Region[]
  /** Add/remove a region and refetch the page so it is worth `feedLimit` rows
   * again — server-side narrowing is the whole reason the filter is not purely
   * a render concern. */
  toggleFeedRegion: (id: Region) => void
  /** Name the reporting channel on each feed card (see
   * `initialFeedShowSource`). Display only — nothing is re-fetched. */
  feedShowSource: boolean
  setFeedShowSource: (on: boolean) => void
  /** Desktop: hide the feed rail and give the map the whole window. Nothing
   * stops being received — the feed's data lives in the store either way, so
   * reopening it shows everything that happened while it was away. */
  feedCollapsed: boolean
  toggleFeed: () => void
  /** How the map draws targets — trail width (or none), marker size, and
   * whether anything animates. Per-device rather than per-account: the phone in
   * a corridor and the TV on the wall want different answers. */
  mapTrail: boolean
  setMapTrail: (on: boolean) => void
  mapTrackWidth: number
  setMapTrackWidth: (px: number) => void
  mapMarkerSize: MapMarkerSize
  setMapMarkerSize: (s: MapMarkerSize) => void
  mapMotion: boolean
  setMapMotion: (on: boolean) => void
  /** Opt-in "gamification" card-analysis layer (off by default). Account-bound:
   * hydrated from the signed-in user on login (authSlice) and persisted to the
   * server on change, so it syncs across the user's devices. The map, alerts and
   * threat logic never read it. */
  gamification: boolean
  /** Toggle + persist to the account. */
  setGamification: (on: boolean) => void
  /** Set the local state only (used to hydrate from the user on login). */
  hydrateGamification: (on: boolean) => void
}

export const createPrefsSlice: StateCreator<RadarState, [], [], PrefsSlice> = (set, get) => ({
  sheetHeight: initialSheetHeight(),
  setSheetHeight: (h) => {
    safeSet(STORAGE_KEYS.sheetHeight, h)
    set({ sheetHeight: h })
  },
  feedTextSize: initialFeedTextSize(),
  setFeedTextSize: (s) => {
    safeSet(STORAGE_KEYS.feedTextSize, s)
    set({ feedTextSize: s })
  },
  feedLimit: initialFeedLimit(),
  setFeedLimit: (n) => {
    safeSet(STORAGE_KEYS.feedLimit, String(n))
    set({ feedLimit: n })
  },
  feedExtraRegions: initialFeedExtraRegions(),
  toggleFeedRegion: (id) => {
    const s = get()
    const home = currentRegion(s)
    if (id === home) return
    const next = s.feedExtraRegions.includes(id)
      ? s.feedExtraRegions.filter((r) => r !== id)
      : [...s.feedExtraRegions, id]
    safeSet(STORAGE_KEYS.feedRegions, JSON.stringify(next))
    set({ feedExtraRegions: next })
    fetchRecentEvents(s.feedLimit, shownRegions(next, home))
      .then(s.setLog)
      .catch(() => {})
  },
  feedShowSource: initialFeedShowSource(),
  setFeedShowSource: (on) => {
    safeSet(STORAGE_KEYS.feedShowSource, on ? '1' : '0')
    set({ feedShowSource: on })
  },
  feedCollapsed: safeGet(STORAGE_KEYS.feedCollapsed) === '1',
  toggleFeed: () =>
    set((s) => {
      const collapsed = !s.feedCollapsed
      safeSet(STORAGE_KEYS.feedCollapsed, collapsed ? '1' : '0')
      return { feedCollapsed: collapsed }
    }),
  mapTrail: initialMapTrail(),
  setMapTrail: (on) => {
    safeSet(STORAGE_KEYS.mapTrail, on ? '1' : '0')
    set({ mapTrail: on })
  },
  mapTrackWidth: initialMapTrackWidth(),
  setMapTrackWidth: (px) => {
    safeSet(STORAGE_KEYS.mapTrackWidth, String(px))
    set({ mapTrackWidth: px })
  },
  mapMarkerSize: initialMapMarkerSize(),
  setMapMarkerSize: (size) => {
    safeSet(STORAGE_KEYS.mapMarkerSize, size)
    set({ mapMarkerSize: size })
  },
  mapMotion: initialMapMotion(),
  setMapMotion: (on) => {
    safeSet(STORAGE_KEYS.mapMotion, on ? '1' : '0')
    set({ mapMotion: on })
  },
  gamification: false,
  setGamification: (on) => {
    set({ gamification: on })
    void setGamificationPref(on).catch(() => {})
  },
  hydrateGamification: (on) => set({ gamification: on }),
})
