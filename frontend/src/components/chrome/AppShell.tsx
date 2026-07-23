import type { ReactNode } from 'react'

import SettingsDrawer from './SettingsDrawer'
import SplashScreen from './SplashScreen'
import TopBar from './TopBar'
import UpdateToast from './UpdateToast'

/** The persistent app shell wrapping every route: a top bar (which carries the
 * navigation on every viewport), the routed page in a bounded slot, the settings
 * drawer, and the global SW-update toast. The PWA-launch splash lives here, not
 * in the map route, so it plays once per app launch — not every time the map
 * route remounts on in-app navigation (back to Мапа from Journal etc.). */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <SplashScreen />
      <TopBar />
      <div className="relative min-h-0 flex-1">{children}</div>
      <SettingsDrawer />
      <UpdateToast />
    </div>
  )
}
