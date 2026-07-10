import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { startAnimatedFavicon } from './animatedFavicon'
import './i18n'
import './index.css'

startAnimatedFavicon()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
