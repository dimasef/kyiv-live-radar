import type { Pt } from "../../lib/geo";

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

// Inspect fly-to zoom — kept modest so a lone sighting lands with district
// context, not at street level. INSPECT_MAX_ZOOM caps flyToBounds for a short track.
export const INSPECT_ZOOM = 11;
export const INSPECT_MAX_ZOOM = 12;

/** Raion air-alert fill (AlertZoneLayer). Drawn UNDER the Kyiv raion outlines
 * and every marker, so the fill has to read at a glance while staying quiet
 * enough that a target on top of it is still the loudest thing on the map. */
export const ZONE_STYLES = {
  alert: { color: '#ef4444', weight: 1, opacity: 0.5, fillColor: '#ef4444', fillOpacity: 0.14 },
  clear: { color: '#475569', weight: 1, opacity: 0.28, fillColor: '#475569', fillOpacity: 0.03 },
  // Provider unreachable: dashed and colourless — visibly "no data", never a
  // silent all-clear.
  stale: {
    color: '#64748b', weight: 1, opacity: 0.3, dashArray: '4 4',
    fillColor: '#64748b', fillOpacity: 0.02,
  },
} as const

export const DISTRICT_STYLE = {
  color: "#64748b",
  weight: 1,
  opacity: 0.45,
  fillColor: "#334155",
  fillOpacity: 0.1,
};
