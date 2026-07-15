import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { ChangelogPage } from './components/changelog'
import { RawMessagesPage } from './components/raw'
import { CHANGELOG_PATH, RAW_MESSAGES_PATH, useRoute } from './router'
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

/** Tiny top-level router: the changelog and raw-message debug view are their
 * own routes; everything else is the radar app (whose data-fetching hooks
 * then only run there — see store/bootstrap.ts). */
function Root() {
  const route = useRoute()
  if (route === CHANGELOG_PATH) return <ChangelogPage />
  if (route === RAW_MESSAGES_PATH) return <RawMessagesPage />
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
