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

export const DISTRICT_STYLE = {
  color: "#64748b",
  weight: 1,
  opacity: 0.45,
  fillColor: "#334155",
  fillOpacity: 0.1,
};
