import L from "leaflet";

import { aftermathMarkerSvg } from "@/aftermathIcons";

// Split out of aftermathIcons.ts (2026-09-12) — see threatDivIcon.ts for why:
// the `import L from 'leaflet'` this needed was pulling Leaflet into every
// consumer of that file, including the journal page.

export function aftermathDivIcon({ size = 22 }: { size?: number } = {}): L.DivIcon {
  return L.divIcon({
    html: aftermathMarkerSvg({ size }),
    className: "threat-icon",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}
