import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { AppShell } from './components/chrome'
import {
  ACCOUNT_PATH,
  CHANGELOG_PATH,
  isAdminRoute,
  isCollectionRoute,
  isJournalRoute,
  useRoute,
  userRouteId,
} from './router'

// Secondary routes are lazy so the initial bundle is just the map (the critical
// path). The admin console, journal, changelog data and account page each load
// on demand — faster first paint, which matters most on a phone at night.
const AdminPage = lazy(() => import('./components/admin/AdminPage'))
const AccountPage = lazy(() => import('./components/auth/AccountPage'))
const ContactPage = lazy(() => import('./components/auth/ContactPage'))
const CollectionPage = lazy(() => import('./components/game/CollectionPage'))
const ChangelogPage = lazy(() => import('./components/changelog/ChangelogPage'))
const ThreatJournalPage = lazy(() => import('./components/journal/ThreatJournalPage'))
import { useRadar } from './store'
import './i18n'
import './index.css'

// Capture the deferred install prompt so InstallControl can trigger the native
// install sheet on demand (Chromium/Android/desktop). The SW itself is
// registered by UpdateToast's useRegisterSW. iOS Safari fires no such event —
// InstallControl shows a manual "Add to Home Screen" hint there instead.
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  useRadar.getState().setInstallPrompt(e)
})
window.addEventListener('appinstalled', () => {
  useRadar.getState().setInstallPrompt(null)
})

// Restore any signed-in session from the stored refresh token, once at boot —
// module scope (not a component effect) so it runs a single time across every
// route, not just the radar app, and isn't double-fired by StrictMode.
void useRadar.getState().refreshSession()

/** Tiny top-level router: the changelog, journal and raw-message debug view are
 * their own routes; everything else is the radar app (whose data-fetching hooks
 * then only run there — see store/bootstrap.ts). Every route renders inside the
 * persistent AppShell (top bar + mobile bottom nav + settings drawer + the
 * global SW-update toast), so navigation and status are consistent everywhere. */
function Root() {
  const route = useRoute()
  const page =
    route === CHANGELOG_PATH ? (
      <ChangelogPage />
    ) : isJournalRoute(route) ? (
      <ThreatJournalPage />
    ) : isAdminRoute(route) ? (
      <AdminPage />
    ) : route === ACCOUNT_PATH ? (
      <AccountPage />
    ) : userRouteId(route) != null ? (
      <ContactPage />
    ) : isCollectionRoute(route) ? (
      <CollectionPage />
    ) : (
      <App />
    )
  return (
    <AppShell>
      <Suspense fallback={<RouteFallback />}>{page}</Suspense>
    </AppShell>
  )
}

function RouteFallback() {
  return (
    <div className="flex h-full items-center justify-center bg-ink-950 text-xs text-slate-500">
      Завантаження…
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
