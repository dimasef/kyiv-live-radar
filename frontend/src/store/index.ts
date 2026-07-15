import { create } from 'zustand'

import { createAlertsSlice } from './alertsSlice'
import { createConnectionSlice } from './connectionSlice'
import { createDistrictsSlice } from './districtsSlice'
import { createHomeSlice } from './homeSlice'
import { createIncidentsSlice } from './incidentsSlice'
import { createNoticesSlice } from './noticesSlice'
import { createPwaSlice } from './pwaSlice'
import { createThreatsSlice } from './threatsSlice'
import type { RadarState } from './types'
import { createWsSlice } from './wsSlice'

export type { Home } from './homeSlice'
export type { RadarState } from './types'

export const useRadar = create<RadarState>()((...a) => ({
  ...createDistrictsSlice(...a),
  ...createThreatsSlice(...a),
  ...createNoticesSlice(...a),
  ...createIncidentsSlice(...a),
  ...createAlertsSlice(...a),
  ...createConnectionSlice(...a),
  ...createHomeSlice(...a),
  ...createPwaSlice(...a),
  ...createWsSlice(...a),
}))
