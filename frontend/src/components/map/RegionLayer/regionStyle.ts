import type { PathOptions } from 'leaflet'

/** The app accent (--phosphor). Hard-coded because Leaflet paints SVG
 * attributes, not CSS variables. */
const PHOSPHOR = '#22d3ee'

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
      color: PHOSPHOR, weight: 1.6, opacity: 0.75,
      fillColor: PHOSPHOR, fillOpacity: 0.02,
    }
  }
  if (inFeed) {
    return {
      color: PHOSPHOR, weight: 1.3, opacity: 0.45,
      fillColor: PHOSPHOR, fillOpacity: 0.015,
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

/** Pointing at an oblast that is NOT in the feed: a preview of what adding it
 * would look like — the same phosphor as a chosen region, held below its
 * opacity so hovering never reads as already-added. Deliberately not applied to
 * a region already in the feed: this cue is the invitation to add one.
 *
 * Applied with `setStyle`, which MERGES — the dashed edge of a region with no
 * coverage yet survives the hover, so "nothing here yet" is not hidden by it.
 */
export function regionHoverStyle(): PathOptions {
  return {
    color: PHOSPHOR, weight: 1.4, opacity: 0.4,
    fillColor: PHOSPHOR, fillOpacity: 0.03,
  }
}
