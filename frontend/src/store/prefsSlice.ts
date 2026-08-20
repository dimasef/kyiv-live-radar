import type { StateCreator } from 'zustand'

import { setGamificationPref } from '@/api'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'

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

/** Whether the feed lists sightings from the watched regions OTHER than Kyiv's
 * own pool (today that means Чернігівщина). Defaults to on — the reader has
 * been seeing them, and a filter that hides data by default is a filter nobody
 * knows is there. Affects the FEED ONLY; the map is a separate question. */
function initialFeedOtherRegions(): boolean {
  return safeGet(STORAGE_KEYS.feedOtherRegions) !== '0'
}

/** Whether a feed card names the channel the message came from. Defaults to on:
 * with several spotter channels of unequal reliability in one timeline, who said
 * it is part of how much to believe it — the map popup has always named the
 * source, and the feed was the one place that dropped it. Off is for when the
 * feed is scrolling too fast to want a second line per card. */
function initialFeedShowSource(): boolean {
  return safeGet(STORAGE_KEYS.feedShowSource) !== '0'
}

export interface PrefsSlice {
  sheetHeight: SheetHeight
  setSheetHeight: (h: SheetHeight) => void
  feedTextSize: FeedTextSize
  setFeedTextSize: (s: FeedTextSize) => void
  feedLimit: FeedLimit
  setFeedLimit: (n: FeedLimit) => void
  /** Show other watched regions' sightings in the event feed (see
   * `initialFeedOtherRegions`). The map ignores this. */
  feedOtherRegions: boolean
  setFeedOtherRegions: (on: boolean) => void
  /** Name the reporting channel on each feed card (see
   * `initialFeedShowSource`). Display only — nothing is re-fetched. */
  feedShowSource: boolean
  setFeedShowSource: (on: boolean) => void
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

export const createPrefsSlice: StateCreator<RadarState, [], [], PrefsSlice> = (set) => ({
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
  feedOtherRegions: initialFeedOtherRegions(),
  setFeedOtherRegions: (on) => {
    safeSet(STORAGE_KEYS.feedOtherRegions, on ? '1' : '0')
    set({ feedOtherRegions: on })
  },
  feedShowSource: initialFeedShowSource(),
  setFeedShowSource: (on) => {
    safeSet(STORAGE_KEYS.feedShowSource, on ? '1' : '0')
    set({ feedShowSource: on })
  },
  gamification: false,
  setGamification: (on) => {
    set({ gamification: on })
    void setGamificationPref(on).catch(() => {})
  },
  hydrateGamification: (on) => set({ gamification: on }),
})
