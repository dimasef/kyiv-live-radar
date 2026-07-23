import type { StateCreator } from 'zustand'

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

export interface PrefsSlice {
  sheetHeight: SheetHeight
  setSheetHeight: (h: SheetHeight) => void
  feedTextSize: FeedTextSize
  setFeedTextSize: (s: FeedTextSize) => void
  feedLimit: FeedLimit
  setFeedLimit: (n: FeedLimit) => void
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
})
