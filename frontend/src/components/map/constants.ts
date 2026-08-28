import type { Pt } from "@/lib/geo";

export const KYIV_CENTER: [number, number] = [50.4501, 30.5234];
export const KYIV_PT: Pt = { lat: KYIV_CENTER[0], lon: KYIV_CENTER[1] };

// Administrative bounding box of the city [[south, west], [north, east]] — the
// map fits these on load so the whole of Kyiv is visible regardless of viewport
// size, instead of a hardcoded zoom that clips on some screens.
export const KYIV_BOUNDS: [[number, number], [number, number]] = [
  [50.21, 30.24],
  [50.59, 30.83],
];

// How far out the map may be zoomed — wide enough to put Kyiv in a European
// context (where a raid came from), which is the only reason to leave the city
// at all. At this level a 390px phone spans ≈2400 km and a 1440px desktop
// ≈9000 km, so Europe fits on either.
//
// One step further is the actual floor worth having: at zoom 3 the whole world
// is 2048px wide, so any screen wider than that starts repeating copies of it
// side by side — a map of three Kyivs helps nobody.
export const MIN_ZOOM = 4;

// One world, not the endless carousel Leaflet pans by default. Latitude stops
// at 85.05° because that is where Web Mercator itself ends — the poles are at
// infinity in this projection, so there is nothing beyond it to show.
export const WORLD_BOUNDS: [[number, number], [number, number]] = [
  [-85.05, -180],
  [85.05, 180],
];

// CARTO stopped serving its raster basemaps anonymously: a keyless request
// still returns the tile, but with an "API KEY REQUIRED" watermark burned into
// the PNG by their CDN — nothing on our side can strip it. A key (free tier,
// 5M tiles/month, requested at carto.com/basemaps/apikey) removes it. Left
// optional so a checkout with no .env still renders a map, watermark and all.
const CARTO_KEY = import.meta.env.VITE_CARTO_KEY;
export const BASEMAP_URL =
  "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" +
  (CARTO_KEY ? `?key=${CARTO_KEY}` : "");

// Above this many tracks ON SCREEN at once, every target stops animating on its
// own (see ThreatLayer's `lean`). The second half of the same budget: viewport
// culling decides WHICH tracks are drawn, this decides whether the survivors
// may move.
//
// Per-target motion does not survive a crowd anyway: three separate signals
// (two pulse rings, a crawling dash, a drifting glyph) multiplied by a hundred
// targets is not "a hundred live contacts", it is noise. 24 is where a
// phone-sized viewport is already dense enough that a reader tracks the CLUSTER
// rather than any one contact. The static forms all remain — a lean track keeps
// its dashes, its head and one ring, it just stops moving.
export const MOTION_BUDGET = 24;

// Inspect fly-to zoom — kept modest so a lone sighting lands with district
// context, not at street level. INSPECT_MAX_ZOOM caps flyToBounds for a short track.
export const INSPECT_ZOOM = 11;
export const INSPECT_MAX_ZOOM = 12;

// Slack around the lit raions when the alert layer widens the view
// (controllers/ZoneAutoFit). Leaflet applies a `padding` to both sides of each
// axis, so the vertical figure is what has to clear the map's lower furniture —
// the mobile sheet handle and the control cluster sit over it, and a raion
// tucked under them is not visible for this purpose.
export const ZONE_FIT_PADDING: [number, number] = [40, 72];

// How far ZoneAutoFit may pull BACK. Fitting every lit raion unconditionally
// landed the view at zoom 7, where the scale bar reads 50 km and a raion is a
// smudge; 8 (scale bar 30 km) keeps the names and the lit edges legible.
//
// The trade is deliberate: on a narrow screen the watched area no longer fits
// in one frame at this zoom, so the far north can stay off-view until panned
// to. The fit still only ever zooms OUT — this just stops it short.
export const ZONE_FIT_MIN_ZOOM = 8;

// Where the oblast layer takes over (RegionLayer). One step below
// ZONE_FIT_MIN_ZOOM: 8 is documented above as the level where a raion stops
// being legible, so 7 is the first level where the oblast is the meaningful
// unit. With MIN_ZOOM at 4 that leaves a comfortable four-level band.
export const REGION_LAYER_MAX_ZOOM = 7;

/** Raion air-alert outlines (AlertZoneLayer). Drawn UNDER the Kyiv raion
 * outlines and every marker, so the state has to read at a glance while staying
 * quiet enough that a target on top of it is still the loudest thing on the map.
 *
 * An alerted raion carries NO fill: during a real raid the sirens cover most of
 * the oblast at once, and a wash — even at 0.14 — turned the map into one red
 * sheet with the targets floating on it. The state is drawn as a lit edge
 * instead (see ZONE_GLOW / ZoneGlowDefs), which survives being tiled across a
 * dozen neighbouring raions because it never crosses their shared borders.
 * `clear` and `stale` keep their whisper of a fill: they are the quiet states,
 * and there is nothing to drown out. */
export const ZONE_STYLES = {
  // fillOpacity 0.01 is a HIT AREA, not a colour. SVG hit-testing only sees a
  // painted fill, so `fill: false` (or a flat 0) would leave the raion reachable
  // by its 1.4px border alone — and hovering the middle is how its name and how
  // long the siren has been up are read. At 1% on a dark basemap it is invisible.
  alert: {
    color: '#ef4444', weight: 1.4, opacity: 0.9,
    fillColor: '#ef4444', fillOpacity: 0.01,
  },
  clear: { color: '#475569', weight: 1, opacity: 0.28, fillColor: '#475569', fillOpacity: 0.03 },
  // Provider unreachable: dashed and colourless — visibly "no data", never a
  // silent all-clear.
  stale: {
    color: '#64748b', weight: 1, opacity: 0.3, dashArray: '4 4',
    fillColor: '#64748b', fillOpacity: 0.02,
  },
} as const

/** Per-raion nudges for the standing centre label, in pixels, [x, y] with y
 * positive downward.
 *
 * Leaflet pins a polygon's tooltip to the centre of its BOUNDS, which for a
 * concave or lopsided raion is not where the raion visually is — the label ends
 * up crowding a neighbour's border, or sitting outside the shape altogether.
 * Only the raions that actually land badly are listed; everything else is
 * centred fine and stays out of this table.
 *
 * Pixels rather than a geographic shift on purpose: the correction is against
 * the SHAPE of the outline, which is a screen-space problem, and this keeps the
 * nudge the same modest distance at every zoom instead of growing with it. */
export const ZONE_LABEL_NUDGE: Record<string, [number, number]> = {
  'kyiv-obl-boryspilskyi': [0, 22],
  'kyiv-obl-brovarskyi': [0, 22],
  'chernihiv-obl-nizhynskyi': [0, -22],
}

/** The lit edge itself. Painted by an SVG filter on a second, non-interactive
 * copy of the polygon — the shape goes in, only the inner band comes out.
 *
 * `spreadPx` is in map pixels, so the glow keeps a constant visual weight while
 * the raion under it grows and shrinks with zoom. Zoomed far out a small raion
 * is narrower than the glow and simply lights up whole, which is the right
 * reading at that scale anyway. */
export const ZONE_GLOW = {
  color: '#ef4444',
  opacity: 0.55,
  spreadPx: 6,
  /** Full-alpha source for the filter to eat; never seen as a fill itself. */
  style: { fillColor: '#ef4444', fillOpacity: 1, stroke: false, interactive: false },
} as const

/** The all-clear flash: the same lit edge in green, shown for a few seconds when
 * a raion's siren is called off and then taken away (see store/zonesSlice
 * `zoneAllClear`).
 *
 * A moment, not a state — deliberately so. «Відбій» is the one transition worth
 * interrupting a glance for, but a raion that has been quiet for an hour must
 * look like the basemap, or the map fills with reassurance and the sirens stop
 * standing out. Brighter than the red glow because it only ever exists for six
 * seconds, against a border that has just gone dark.
 */
export const ZONE_ALL_CLEAR = {
  color: '#22c55e',
  opacity: 0.7,
  spreadPx: 7,
  style: { fillColor: '#22c55e', fillOpacity: 1, stroke: false, interactive: false },
} as const

export const DISTRICT_STYLE = {
  color: "#64748b",
  weight: 1,
  opacity: 0.45,
  fillColor: "#334155",
  fillOpacity: 0.1,
};
