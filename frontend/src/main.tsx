import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { AccountPage } from './components/auth'
import { ChangelogPage } from './components/changelog'
import { UpdateToast } from './components/chrome'
import { ThreatJournalPage } from './components/journal'
import { RawMessagesPage } from './components/raw'
import {
  ACCOUNT_PATH,
  CHANGELOG_PATH,
  RAW_MESSAGES_PATH,
  THREAT_JOURNAL_PATH,
  useRoute,
} from './router'
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
 * then only run there — see store/bootstrap.ts). UpdateToast lives HERE, not in
 * App: it is the app's single SW-registration point and the "new version" banner
 * must appear on every route, including a tab left open on a secondary page. */
function Root() {
  const route = useRoute()
  const page =
    route === CHANGELOG_PATH ? (
      <ChangelogPage />
    ) : route === THREAT_JOURNAL_PATH ? (
      <ThreatJournalPage />
    ) : route === RAW_MESSAGES_PATH ? (
      <RawMessagesPage />
    ) : route === ACCOUNT_PATH ? (
      <AccountPage />
    ) : (
      <App />
    )
  return (
    <>
      {page}
      <UpdateToast />
    </>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
