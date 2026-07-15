import type { StateCreator } from 'zustand'

import type { Alert } from '@/types'

import type { RadarState } from './types'

export interface AlertsSlice {
  alerts: Alert[]
  setAlerts: (a: Alert[]) => void
  /** Official alert windows (тривога/відбій) — replace by id since, unlike
   * notices (append-only), the SAME alert mutates in place (start -> end). */
  upsertAlert: (alert: Alert) => void
}

export const createAlertsSlice: StateCreator<RadarState, [], [], AlertsSlice> = (set) => ({
  alerts: [],
  setAlerts: (a) => set({ alerts: a }),
  upsertAlert: (alert) =>
    set((s) => ({ alerts: [alert, ...s.alerts.filter((a) => a.id !== alert.id)] })),
})
