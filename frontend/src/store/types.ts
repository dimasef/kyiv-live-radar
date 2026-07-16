import type { AlertsSlice } from './alertsSlice'
import type { AxesSlice } from './axesSlice'
import type { ConnectionSlice } from './connectionSlice'
import type { DistrictsSlice } from './districtsSlice'
import type { HomeSlice } from './homeSlice'
import type { IncidentsSlice } from './incidentsSlice'
import type { NoticesSlice } from './noticesSlice'
import type { PrefsSlice } from './prefsSlice'
import type { PwaSlice } from './pwaSlice'
import type { ThreatsSlice } from './threatsSlice'
import type { WsSlice } from './wsSlice'

export type RadarState = DistrictsSlice &
  ThreatsSlice &
  NoticesSlice &
  IncidentsSlice &
  AxesSlice &
  AlertsSlice &
  ConnectionSlice &
  HomeSlice &
  PwaSlice &
  PrefsSlice &
  WsSlice
