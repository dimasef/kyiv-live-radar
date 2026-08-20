import { Maximize, Minimize } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { mapControlClass } from './controlStyles'

/** Puts the whole page into fullscreen — the map is the page, and a raid is
 * exactly when the browser chrome is worth losing.
 *
 * Renders nothing where the API is missing (iPhone Safari allows fullscreen for
 * video only, and TV browsers vary): a button that silently does nothing is
 * worse than no button. */
export default function FullscreenButton() {
  const { t } = useTranslation()
  const [full, setFull] = useState(() => document.fullscreenElement != null)

  // Genuinely external state: Esc, F11 and the browser's own UI all leave
  // fullscreen without telling React, so the icon must follow the DOM's event.
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement != null)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  if (!document.fullscreenEnabled) return null

  const toggle = () => {
    // Rejects when the gesture isn't trusted or the OS refuses — nothing to do
    // about it, and an unhandled rejection would surface as a console error.
    const done = full ? document.exitFullscreen() : document.documentElement.requestFullscreen()
    void done?.catch(() => {})
  }

  const Icon = full ? Minimize : Maximize
  return (
    <button
      onClick={toggle}
      aria-label={t(full ? 'legendCtl.exitFullscreen' : 'legendCtl.fullscreen')}
      title={t(full ? 'legendCtl.exitFullscreen' : 'legendCtl.fullscreen')}
      className={mapControlClass(full)}
    >
      <Icon size={17} />
    </button>
  )
}
