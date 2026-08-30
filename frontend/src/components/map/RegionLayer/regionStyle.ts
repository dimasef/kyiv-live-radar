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
    // The region the reader follows: the heaviest, brightest GREY. It used to be
    // phosphor, and that was the whole problem — the app accent means "live
    // threat data" everywhere else on this map, so an oblast wearing it looked
    // like something was happening there. A reader who had never opened this
    // layer read their own region lighting up as an alert, not as a setting.
    // State is carried by the badge (regionBadge) now, and the outline is only
    // geography.
    return {
      color: '#cbd5e1', weight: 1.8, opacity: 0.55,
      fillColor: '#cbd5e1', fillOpacity: 0.02,
    }
  }
  if (inFeed) {
    return {
      color: '#94a3b8', weight: 1.4, opacity: 0.4,
      fillColor: '#94a3b8', fillOpacity: 0.015,
    }
  }
  // Out of the feed: present, clickable, visibly not being listened to. A
  // region with no coverage yet is dashed on top of that, so "you have not
  // added this" and "there is nothing here yet" stay distinguishable.
  return {
    color: '#64748b', weight: 1, opacity: active ? 0.25 : 0.2,
    ...(active ? {} : { dashArray: '5 5' }),
    fillColor: '#64748b', fillOpacity: 0.01,
  }
}

/** Pointing at an oblast that is NOT in the feed: a preview of what acting on it
 * would do. Deliberately not applied to a region already in the feed — this cue
 * is the invitation to add one.
 *
 * The one place the accent survives on this layer, and it survives BECAUSE it is
 * transient: phosphor under the cursor reads as "this responds to you", where
 * phosphor sitting permanently on a region read as "something is happening
 * there". Nothing on a touch screen ever enters this state (no hover), which is
 * why those devices get a badge instead.
 *
 * Applied with `setStyle`, which MERGES — the dashed edge of a region with no
 * coverage yet survives the hover, so "nothing here yet" is not hidden by it.
 */
export function regionHoverStyle(): PathOptions {
  return {
    color: PHOSPHOR, weight: 1.4, opacity: 0.45,
    fillColor: PHOSPHOR, fillOpacity: 0.03,
  }
}
