import { GeoJSON } from "react-leaflet";

import { useRadar } from "../../store";
import { threatColor } from "../../theme";

/** When a city-wide threat is active (a ballistic-phase alert with no raion to
 * localize), the whole city is under threat — pulse every raion boundary in the
 * threat colour. City-scope threats are skipped as map points (MapView), so this
 * is their only map presence besides the banner. */
export default function CitywidePulse() {
  const threats = useRadar((s) => s.threats);
  const boundaries = useRadar((s) => s.boundaries);

  const city = Object.values(threats).find((t) => t.scope === "city" && !t.closed_at);
  if (!city || boundaries.length === 0) return null;
  const color = threatColor(city);

  return (
    <>
      {boundaries.map((b) => (
        <GeoJSON
          key={`citypulse-${b.id}-${color}`}
          data={b.geojson}
          interactive={false}
          style={{
            color,
            weight: 2,
            opacity: 0.55,
            fillColor: color,
            fillOpacity: 0.05,
            className: "citywide-pulse",
          }}
        />
      ))}
    </>
  );
}
