import { create } from 'zustand'

import { createAlertsSlice } from './alertsSlice'
import { createAuthSlice } from './authSlice'
import { createAxesSlice } from './axesSlice'
import { createConnectionSlice } from './connectionSlice'
import { createDistrictsSlice } from './districtsSlice'
import { createFriendsSlice } from './friendsSlice'
import { createGameSlice } from './gameSlice'
import { createHomeSlice } from './homeSlice'
import { createIncidentsSlice } from './incidentsSlice'
import { createNoticesSlice } from './noticesSlice'
import { createNotifySlice } from './notifySlice'
import { createPrefsSlice } from './prefsSlice'
import { createPwaSlice } from './pwaSlice'
import { createThreatsSlice } from './threatsSlice'
import type { RadarState } from './types'
import { createUiSlice } from './uiSlice'
import { createWsSlice } from './wsSlice'

export type { Home } from './homeSlice'
export type { RadarState } from './types'

export const useRadar = create<RadarState>()((...a) => ({
  ...createDistrictsSlice(...a),
  ...createThreatsSlice(...a),
  ...createNoticesSlice(...a),
  ...createIncidentsSlice(...a),
  ...createAxesSlice(...a),
  ...createAlertsSlice(...a),
  ...createConnectionSlice(...a),
  ...createHomeSlice(...a),
  ...createFriendsSlice(...a),
  ...createGameSlice(...a),
  ...createPwaSlice(...a),
  ...createPrefsSlice(...a),
  ...createNotifySlice(...a),
  ...createWsSlice(...a),
  ...createAuthSlice(...a),
  ...createUiSlice(...a),
}))
