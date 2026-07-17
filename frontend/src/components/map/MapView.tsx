import L from "leaflet";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Circle,
  GeoJSON,
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
} from "react-leaflet";

import { useRadar } from "../../store";
import { HOME_COLOR } from "../../theme";
import AxisLayer from "./AxisLayer";
import CitywidePulse from "./CitywidePulse";
import { KYIV_BOUNDS, DISTRICT_STYLE } from "./constants";
import { HomeController, InspectController, ResizeHandler } from "./controllers";
import IncidentHighlight from "./IncidentHighlight";
import MapLegend from "./MapLegend";
import ThreatLayer from "./ThreatLayer";

const homeIcon = L.divIcon({
  className: "home-marker",
  html: `<svg width="22" height="22" viewBox="0 0 24 24" style="filter:drop-shadow(0 0 6px rgba(56,189,248,.6))">
    <path d="M12 3 L21 11 L18 11 L18 20 L14 20 L14 14 L10 14 L10 20 L6 20 L6 11 L3 11 Z"
      fill="${HOME_COLOR}" stroke="#0b0f14" stroke-width="1"/></svg>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

export default function MapView() {
  const { t } = useTranslation();
  const threats = useRadar((s) => s.threats);
  const boundaries = useRadar((s) => s.boundaries);
  const home = useRadar((s) => s.home);
  const placingHome = useRadar((s) => s.placingHome);
  const inspectedThreat = useRadar((s) => s.inspectedThreat);
  const [map, setMap] = useState<L.Map | null>(null);

  // A track being inspected might already be live (in `threats`) — in that
  // case the live copy has fresher data, so just highlight it in place rather
  // than rendering a second, stale layer on top of it.
  const inspectedIsLive = inspectedThreat != null && inspectedThreat.id in threats;

  return (
    <div className="relative h-full w-full">
      <MapContainer
        ref={setMap}
        bounds={KYIV_BOUNDS}
        boundsOptions={{ padding: [20, 20] }}
        className={placingHome ? "placing-home" : undefined}
        style={{ height: "100%", width: "100%", background: "#05080d" }}
      >
        <TileLayer
          attribution="&copy; OpenStreetMap &copy; CARTO"
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />

        {/* Real OSM raion boundaries — a non-interactive context layer: clicks
            pass through to the map (pan / home placement) and no focus outline. */}
        {boundaries.map((b) => (
          <GeoJSON key={b.id} data={b.geojson} style={DISTRICT_STYLE} interactive={false} />
        ))}
        {/* Attack heat (raions under an active incident) + city-wide pulse layer
            over the inert base boundaries. */}
        <IncidentHighlight />
        <CitywidePulse />

        <ResizeHandler />
        <HomeController />
        <InspectController />

        {home && (
          <>
            <Circle
              center={[home.lat, home.lon]}
              radius={home.radiusKm * 1000}
              pathOptions={{
                color: HOME_COLOR,
                fillColor: HOME_COLOR,
                fillOpacity: 0.06,
                weight: 1,
              }}
            />
            <Marker position={[home.lat, home.lon]} icon={homeIcon}>
              <Tooltip direction="top" offset={[0, -18]}>
                {t("legend.home")} · {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
              </Tooltip>
            </Marker>
          </>
        )}

        {Object.values(threats).map((th) => (
          <ThreatLayer key={th.id} threat={th} highlighted={inspectedThreat?.id === th.id} />
        ))}
        {/* The inspected track isn't currently live (closed/evicted) — render
            it from its independently-fetched event history. */}
        {inspectedThreat && !inspectedIsLive && (
          <ThreatLayer threat={inspectedThreat} highlighted />
        )}
      </MapContainer>
      <AxisLayer map={map} />
      <MapLegend />
    </div>
  );
}
