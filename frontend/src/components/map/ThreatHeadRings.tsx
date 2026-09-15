import { CircleMarker } from "react-leaflet";

import type { Pt } from "@/lib/geo";

/** --phosphor, the app's accent — spelled out because this is a Leaflet path
 * option, not a class. */
const PICK_COLOR = "#22d3ee";

export default function ThreatHeadRings({
  head,
  highlighted,
  color,
  dim,
  corroborated,
  pickable,
}: {
  head: Pt;
  highlighted: boolean;
  color: string;
  dim: number;
  corroborated: boolean;
  pickable: boolean;
}) {
  return (
    <>
      {/* Corroboration halo — a faint ring behind the head when >= 2 independent
          sources agree, so a well-attested target reads as heavier at a glance. */}
      {corroborated && (
        <CircleMarker
          center={[head.lat, head.lon]}
          radius={highlighted ? 16 : 13}
          interactive={false}
          pathOptions={{
            color,
            weight: 1.5,
            opacity: 0.5 * dim,
            fillColor: color,
            fillOpacity: 0.06,
          }}
        />
      )}
      {/* Ring marking a destination the armed sighting can be dropped onto —
          same idiom as the corroboration halo, in the accent colour so pick
          mode reads as a mode and not as new evidence. */}
      {pickable && (
        <CircleMarker
          center={[head.lat, head.lon]}
          radius={18}
          interactive={false}
          pathOptions={{ color: PICK_COLOR, weight: 2, opacity: 0.9, dashArray: "4 4", fill: false }}
        />
      )}
    </>
  );
}
