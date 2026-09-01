/** All localStorage keys the app uses, namespaced klr-* to avoid collisions
 * with anything else that might share the origin. */
export const STORAGE_KEYS = {
  home: 'klr-home',
  // Which raion the home point falls in, as {lat, lon, zoneId}. The coordinates
  // are stored WITH the answer so a moved home invalidates the cache by itself;
  // caching at all is what lets the banner paint the right raion on the first
  // frame after a reload instead of flashing someone else's siren.
  homeZone: 'klr-home-zone',
  legendOpen: 'klr-legend-open',
  // Whether the raion air-alert layer is switched on. Off by default: it's
  // extra context, and it costs a lazy 76 KB of polygons on first use.
  zoneLayer: 'klr-zone-layer',
  // The episode the status banner was collapsed on ({alert, incident} ids).
  // Survives reloads because an alert outlives the page — but only for that
  // episode; see banners/status.ts stillCollapsed.
  bannerCollapsed: 'klr-banner-collapsed',
  settingsOpen: 'klr-settings-open',
  disclaimerHide: 'klr-disclaimer-hide',
  lang: 'klr-lang',
  installDismiss: 'klr-install-dismiss',
  sheetHeight: 'klr-sheet-height',
  feedTextSize: 'klr-feed-text',
  feedLimit: 'klr-feed-limit',
  // The oblast the reader picked (first run, changeable in settings). Distinct
  // from `home` below: this is WHICH region's data they follow, the home point
  // is WHERE inside it their alerts are measured from. Per-device on purpose.
  region: 'klr-region',
  // Set once the reader has seen the "oblasts are clickable" hint, so it is
  // raised exactly once ever.
  regionHint: 'klr-region-hint',
  // Watched regions OTHER than home that the feed lists, as a JSON id array.
  feedRegions: 'klr-feed-regions',
  // Legacy: the boolean this replaced, back when "other regions" could only
  // mean Чернігівщина. Read once by store/feedRegions.ts and then removed.
  feedOtherRegions: 'klr-feed-other-regions',
  feedShowSource: 'klr-feed-source',
  // Desktop only: the event feed collapsed to give the map the full width.
  // Mobile has the bottom sheet for the same job and ignores this.
  feedCollapsed: 'klr-feed-collapsed',
  // The first-run "mark your home" card was dismissed. Sticky on purpose: an
  // offer that returns after being declined is nagging, and the same action
  // stays in Settings forever.
  homeHint: 'klr-home-hint',
  notify: 'klr-notify',
  notifyPrefs: 'klr-notify-prefs',
  // Contact ids whose shared home the user has hidden on their OWN map (local
  // preference only — the contact still shares it; see friendsSlice).
  hiddenContactHomes: 'klr-contacts-hidden',
  // Per-contact marker appearance {color, icon} the user picked, keyed by
  // contact id — local labelling only (see friendsSlice.contactStyles).
  contactStyles: 'klr-contacts-style',
  // The user's own home-marker appearance {color, icon}. Account-bound (only a
  // signed-in user can change it); this is the cache that paints the first
  // frame before /me/home answers — see homeSlice.homeStyle.
  homeStyle: 'klr-home-style',
  // The refresh token (the access token stays in memory only — see api.ts).
  authRefresh: 'klr-auth',
  // Card ids the user has already seen in their collection, keyed by user id
  // ({ [userId]: number[] }) — drives the one-time "just obtained" shimmer.
  seenCards: 'klr-seen-cards',
  // Whether the stats/filters/toolbar block above «Весь фід» is folded away.
  // Persisted because the reason to fold it is that you are reading messages,
  // and that outlives a page load.
  rawControlsCollapsed: 'klr-raw-controls',
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
