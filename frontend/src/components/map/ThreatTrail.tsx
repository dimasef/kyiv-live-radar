import { CircleMarker, Polyline } from "react-leaflet";

import type { Pt } from "@/lib/geo";

export default function ThreatTrail({
  pts,
  color,
  weight,
  dim,
  active,
  live,
  highlighted,
  leaving,
  still,
  moved,
  hasConflict,
}: {
  pts: Pt[];
  color: string;
  weight: number;
  dim: number;
  active: boolean;
  live: boolean;
  highlighted: boolean;
  leaving: boolean;
  still: boolean;
  moved: boolean;
  hasConflict: boolean;
}) {
  const latlngs = pts.map((p) => [p.lat, p.lon] as [number, number]);

  return (
    <>
      {moved && latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity (or
          // going quiet, which drops the flow animation) flips.
          key={`${active ? "live" : "closed"}-${live ? "" : "quiet"}-${highlighted ? "insp" : ""}-${still ? "still" : ""}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight,
            opacity: (active ? 0.8 : highlighted ? 0.75 : 0.45) * dim,
            className:
              [
                // Same dashes either way — a live track still READS as live.
                // Only the crawl is dropped, and it is the expensive half:
                // stroke-dashoffset is not a compositor property, so each
                // flowing track repaints its whole path every frame.
                live && (still ? "track-dashed" : "track-flow"),
                highlighted && "track-inspect",
                leaving && "track-closing",
              ]
                .filter(Boolean)
                .join(" ") || undefined,
            dashArray: !active && hasConflict ? "6 6" : undefined,
          }}
        />
      )}
      {pts.slice(0, -1).map((p, i) => (
        <CircleMarker
          key={i}
          center={[p.lat, p.lon]}
          radius={highlighted ? 4 : 3}
          pathOptions={{
            color,
            fillColor: color,
            fillOpacity: 0.6 * dim,
            weight: highlighted ? 2 : 1,
          }}
        />
      ))}
    </>
  );
}
