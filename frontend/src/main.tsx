import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import ChangelogPage from './components/changelog/ChangelogPage'
import { CHANGELOG_PATH, useRoute } from './router'
import './i18n'
import './index.css'

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
