import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import ChangelogPage from './components/changelog/ChangelogPage'
import { CHANGELOG_PATH, useRoute } from './router'
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

/** Tiny top-level router: the changelog is its own shareable route; everything
 * else is the radar app (whose data-fetching hooks then only run there). */
function Root() {
  const route = useRoute()
  return route === CHANGELOG_PATH ? <ChangelogPage /> : <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
