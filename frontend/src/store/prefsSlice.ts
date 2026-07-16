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

export interface PrefsSlice {
  sheetHeight: SheetHeight
  setSheetHeight: (h: SheetHeight) => void
}

export const createPrefsSlice: StateCreator<RadarState, [], [], PrefsSlice> = (set) => ({
  sheetHeight: initialSheetHeight(),
  setSheetHeight: (h) => {
    safeSet(STORAGE_KEYS.sheetHeight, h)
    set({ sheetHeight: h })
  },
})
