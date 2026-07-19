/** All localStorage keys the app uses, namespaced klr-* to avoid collisions
 * with anything else that might share the origin. */
export const STORAGE_KEYS = {
  home: 'klr-home',
  legendOpen: 'klr-legend-open',
  settingsOpen: 'klr-settings-open',
  disclaimerHide: 'klr-disclaimer-hide',
  lang: 'klr-lang',
  installDismiss: 'klr-install-dismiss',
  sheetHeight: 'klr-sheet-height',
  feedTextSize: 'klr-feed-text',
  geoAsked: 'klr-geo-asked',
  notify: 'klr-notify',
  notifyPrefs: 'klr-notify-prefs',
} as const

/** Reads a localStorage value, swallowing errors (private-browsing/quota/etc.
 * throw rather than just returning null there). */
export function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Writes a localStorage value, swallowing errors. */
export function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore — a UI preference failing to persist shouldn't break the app
  }
}

/** Removes a localStorage value, swallowing errors. */
export function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore
  }
}
