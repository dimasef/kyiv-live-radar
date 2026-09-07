import type L from 'leaflet'

import type { ZoneTone } from './alertZones'

/** The alert layer's stacking order, bottom to top.
 *
 * Declared here because it used to be inherited, and that is the bug this
 * fixes: Leaflet appends a path to its pane when the layer MOUNTS, and these
 * paths remount whenever a raion changes tone. So the last raion to change was
 * always on top — a жовтий neighbour lighting up after a червоний one covered
 * their shared border with amber, and the more serious level lost. Ordering the
 * React array cannot fix that: react-leaflet reorders nothing inside Leaflet
 * once a layer has been added.
 *
 * Reordering this array IS the edit — the z-indices come from the positions.
 */
const STACK = [
  // The lit edges, under every outline. Червоний over жовтий here too: two
  // alerted neighbours' glows meet along their shared border.
  'zone-glow-yellow',
  'zone-glow-red',
  // The «відбій» flash, above the glows and still under the outlines — the same
  // place it occupied when order was just the order these were written in.
  'zone-allclear',
  // Quiet and unknown raions: an outline that says nothing must never cover one
  // that does.
  'zone-quiet',
  'zone-yellow',
  // Червоний above everything else the layer draws — the whole point.
  'zone-red',
] as const

type ZonePane = (typeof STACK)[number]

/** Below Leaflet's overlayPane (400) and above its tilePane (200), so the whole
 * block stays where MapView puts it: BENEATH the raion and oblast outlines,
 * which is what makes it read as background rather than as another set of
 * borders. It only used to land there because AlertZoneLayer mounts before
 * DistrictLayer — meaning a single raion changing tone re-appended its path and
 * jumped over those outlines. Same class of bug as the level one, same fix. */
const BASE_Z = 350

export function paneZIndex(name: ZonePane): number {
  return BASE_Z + STACK.indexOf(name)
}

export const ZONE_GLOW_PANE: Record<'yellow' | 'red', ZonePane> = {
  yellow: 'zone-glow-yellow',
  red: 'zone-glow-red',
}

export const ZONE_ALL_CLEAR_PANE: ZonePane = 'zone-allclear'

export const ZONE_OUTLINE_PANE: Record<ZoneTone, ZonePane> = {
  clear: 'zone-quiet',
  stale: 'zone-quiet',
  yellow: 'zone-yellow',
  red: 'zone-red',
}

/** Create the panes if they aren't there yet.
 *
 * Called during render rather than from an effect, and deliberately: a parent's
 * effect runs AFTER its children's, so a pane created there would not exist when
 * the first GeoJSON asks Leaflet for a renderer in it — and Leaflet throws there
 * rather than falling back to overlayPane. Guarded on `getPane`, so the repeat
 * calls every render makes cost nothing.
 */
export function ensureZonePanes(map: L.Map): void {
  for (const name of STACK) {
    if (map.getPane(name)) continue
    map.createPane(name).style.zIndex = String(paneZIndex(name))
  }
}
