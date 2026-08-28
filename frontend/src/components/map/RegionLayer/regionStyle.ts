import type { PathOptions } from 'leaflet'

/** Outline style for one oblast on the region layer.
 *
 * The fill is a HIT AREA, not a colour — the same trick ZONE_STYLES.alert
 * documents. SVG hit-testing only sees a painted fill, so `fill: false` would
 * leave an oblast clickable by its border alone, and clicking the middle is the
 * whole interaction. At 1–2% on a dark basemap it is invisible.
 */
export function regionStyle(opts: {
  isHome: boolean
  inFeed: boolean
  active: boolean
}): PathOptions {
  const { isHome, inFeed, active } = opts
  if (isHome) {
    // The region the radar is about. Solid and brightest — and not a state the
    // reader can change, so it never reads as "toggled on".
    return {
      color: '#7dd3a0', weight: 1.6, opacity: 0.75,
      fillColor: '#7dd3a0', fillOpacity: 0.02,
    }
  }
  if (inFeed) {
    return {
      color: '#7dd3a0', weight: 1.3, opacity: 0.45,
      fillColor: '#7dd3a0', fillOpacity: 0.015,
    }
  }
  // Out of the feed: present, clickable, visibly not being listened to. A
  // region with no coverage yet is dashed on top of that, so "you have not
  // added this" and "there is nothing here yet" stay distinguishable.
  return {
    color: '#64748b', weight: 1, opacity: active ? 0.3 : 0.22,
    ...(active ? {} : { dashArray: '5 5' }),
    fillColor: '#64748b', fillOpacity: 0.01,
  }
}
