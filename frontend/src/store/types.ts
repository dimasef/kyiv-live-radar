import type { AlertsSlice } from './alertsSlice'
import type { AuthSlice } from './authSlice'
import type { AxesSlice } from './axesSlice'
import type { ClockSlice } from './clockSlice'
import type { ConnectionSlice } from './connectionSlice'
import type { DistrictsSlice } from './districtsSlice'
import type { FriendsSlice } from './friendsSlice'
import type { GameSlice } from './gameSlice'
import type { HomeSlice } from './homeSlice'
import type { IncidentsSlice } from './incidentsSlice'
import type { NoticesSlice } from './noticesSlice'
import type { NotifySlice } from './notifySlice'
import type { PrefsSlice } from './prefsSlice'
import type { PwaSlice } from './pwaSlice'
import type { ThreatsSlice } from './threatsSlice'
import type { UiSlice } from './uiSlice'
import type { WsSlice } from './wsSlice'
import type { ZonesSlice } from './zonesSlice'

export type RadarState = DistrictsSlice &
  ThreatsSlice &
  NoticesSlice &
  IncidentsSlice &
  AxesSlice &
  AlertsSlice &
  ZonesSlice &
  ClockSlice &
  ConnectionSlice &
  HomeSlice &
  FriendsSlice &
  GameSlice &
  PwaSlice &
  PrefsSlice &
  NotifySlice &
  WsSlice &
  AuthSlice &
  UiSlice
