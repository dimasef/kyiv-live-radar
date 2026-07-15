import type { AlertsSlice } from './alertsSlice'
import type { ConnectionSlice } from './connectionSlice'
import type { DistrictsSlice } from './districtsSlice'
import type { HomeSlice } from './homeSlice'
import type { IncidentsSlice } from './incidentsSlice'
import type { NoticesSlice } from './noticesSlice'
import type { PwaSlice } from './pwaSlice'
import type { ThreatsSlice } from './threatsSlice'
import type { WsSlice } from './wsSlice'

export type RadarState = DistrictsSlice &
  ThreatsSlice &
  NoticesSlice &
  IncidentsSlice &
  AlertsSlice &
  ConnectionSlice &
  HomeSlice &
  PwaSlice &
  WsSlice
