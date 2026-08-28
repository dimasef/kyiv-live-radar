import L from "leaflet";
import { useTranslation } from "react-i18next";
import { Circle, Marker, Tooltip } from "react-leaflet";

import { contactMarkerSvg } from "@/lib/contactMarker";
import type { HomeDangerLevel } from "@/lib/homeDanger";
import type { Home } from "@/store/homeSlice";
import { HOME_DANGER_COLORS } from "@/theme";

const HOME_SIZE = 22;

// One icon per (shape, colour) pair; cached so a re-render doesn't rebuild an
// identical divIcon.
const homeIconCache = new Map<string, L.DivIcon>();
function homeIcon(shape: string, color: string, glow: boolean): L.DivIcon {
  const key = `${shape}|${color}|${glow}`;
  let icon = homeIconCache.get(key);
  if (!icon) {
    icon = L.divIcon({
      className: "home-marker",
      html: contactMarkerSvg(shape, color, HOME_SIZE, glow),
      iconSize: [HOME_SIZE, HOME_SIZE],
      iconAnchor: [HOME_SIZE / 2, HOME_SIZE / 2],
    });
    homeIconCache.set(key, icon);
  }
  return icon;
}

/** The user's own home: its radius circle and its marker.
 *
 * The user's colour is theirs only while nothing is coming — an approaching
 * threat repaints the marker orange/red, because that colour is a warning
 * rather than decoration. The chosen SHAPE always survives: it says which
 * marker is yours, which matters most when several are close together. */
export default function HomeMarker({
  home,
  homeStyle,
  danger,
}: {
  home: Home;
  homeStyle: { color: string; icon: string; glow: boolean };
  danger: HomeDangerLevel;
}) {
  const { t } = useTranslation();
  const color = danger === "none" ? homeStyle.color : HOME_DANGER_COLORS[danger];

  return (
    <>
      {/* Keyed by danger level: setStyle doesn't re-apply className, so the
          pulse class only attaches on a fresh mount (same trick as
          CitywidePulse's color-keyed GeoJSON). */}
      <Circle
        key={`home-${danger}`}
        center={[home.lat, home.lon]}
        radius={home.radiusKm * 1000}
        pathOptions={{
          color,
          fillColor: color,
          fillOpacity: danger === "none" ? 0.06 : 0.14,
          weight: danger === "none" ? 1 : 2,
          className: danger === "danger" ? "home-danger-pulse" : undefined,
        }}
      />
      <Marker
        position={[home.lat, home.lon]}
        icon={homeIcon(homeStyle.icon, color, homeStyle.glow)}
      >
        <Tooltip direction="top" offset={[0, -18]}>
          {t("legend.home")} · {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
        </Tooltip>
      </Marker>
    </>
  );
}
