import { CircleMarker } from "react-leaflet";

import type { EchoPt } from "./track";

/** A fix still valid now reads solid, one that has aged out reads faint —
 * "where the other channels saw it just now" versus "where they saw it
 * earlier". */
export default function ThreatEchoDots({
  echoPts,
  color,
  dim,
  now,
}: {
  echoPts: EchoPt[];
  color: string;
  dim: number;
  now: number;
}) {
  return (
    <>
      {echoPts.map((p, i) => {
        const fresh = p.validUntilMs == null || p.validUntilMs > now;
        return (
          <CircleMarker
            key={`echo-${i}`}
            center={[p.lat, p.lon]}
            radius={fresh ? 3.5 : 2.5}
            interactive={false}
            pathOptions={{
              color,
              weight: fresh ? 1.5 : 1,
              opacity: (fresh ? 0.85 : 0.3) * dim,
              fill: false,
              dashArray: "2 2",
            }}
          />
        );
      })}
    </>
  );
}
