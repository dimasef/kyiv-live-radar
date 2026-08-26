import L from "leaflet";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Circle,
  MapContainer,
  Marker,
  ScaleControl,
  TileLayer,
  Tooltip,
} from "react-leaflet";

import { contactMarkerSvg, homeStyleOf } from "@/lib/contactMarker";
import { homeDangerFor, raionIdsForZone } from "@/lib/homeDanger";
import { useRadar } from "@/store";
import { HOME_DANGER_COLORS } from "@/theme";
import AlertZoneLayer from "./AlertZoneLayer";
import AxisLayer from "./AxisLayer";
import CitywidePulse from "./CitywidePulse";
import { BASEMAP_URL, KYIV_BOUNDS, MIN_ZOOM, WORLD_BOUNDS } from "./constants";
import {
  HomeController,
  InspectController,
  ResizeHandler,
  ZoneAutoFit,
} from "./controllers";
import DistrictLayer from "./DistrictLayer";
import FriendLayer from "./FriendLayer";
import HomeCompass from "./HomeCompass";
import HomePlacement from "./HomePlacement";
import MapControls from "./MapControls";
import ThreatLayer from "./ThreatLayer";

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

export default function MapView() {
  const { t } = useTranslation();
  const threats = useRadar((s) => s.threats);
  const boundaries = useRadar((s) => s.boundaries);
  const home = useRadar((s) => s.home);
  const homeStyle = homeStyleOf(useRadar((s) => s.homeStyle));
  const placingHome = useRadar((s) => s.placingHome);
  const inspectedThreat = useRadar((s) => s.inspectedThreat);
  const zoneLayerOn = useRadar((s) => s.zoneLayerOn);
  const [map, setMap] = useState<L.Map | null>(null);

  // A track being inspected might already be live (in `threats`) — in that
  // case the live copy has fresher data, so just highlight it in place rather
  // than rendering a second, stale layer on top of it.
  const inspectedIsLive = inspectedThreat != null && inspectedThreat.id in threats;

  // 25 point-in-polygon tests over every raion boundary, and it depends only
  // on the home zone — without this it re-ran on every live frame, which during
  // a raid is dozens of times a minute.
  const homeRaionIds = useMemo(
    () => (home ? raionIdsForZone(home, boundaries) : []),
    [home, boundaries],
  );
  const danger = home ? homeDangerFor(threats, home, homeRaionIds) : "none";
  // The user's colour is theirs only while nothing is coming: an approaching
  // threat repaints the marker orange/red, because that colour is a warning
  // rather than decoration. The chosen SHAPE always survives — it says which
  // marker is yours, which matters most when several are close together.
  const homeCircleColor = danger === "none" ? homeStyle.color : HOME_DANGER_COLORS[danger];

  return (
    <div className="relative h-full w-full">
      <MapContainer
        ref={setMap}
        bounds={KYIV_BOUNDS}
        boundsOptions={{ padding: [20, 20] }}
        minZoom={MIN_ZOOM}
        // Without these the map is an infinite carousel: Leaflet repeats the
        // world sideways forever, so zooming out to see where a raid came from
        // showed three Europes side by side. Viscosity 1 makes the edge solid
        // rather than springy.
        maxBounds={WORLD_BOUNDS}
        maxBoundsViscosity={1}
        className={placingHome ? "placing-home" : undefined}
        style={{ height: "100%", width: "100%", background: "#05080d" }}
      >
        <TileLayer
          attribution="&copy; OpenStreetMap &copy; CARTO"
          url={BASEMAP_URL}
          maxZoom={20}
          // Stops the tiles themselves from repeating past the antimeridian —
          // maxBounds alone constrains panning, not what gets drawn.
          noWrap
        />

        {/* Official raion air-alert state — background context, so it goes
            under the Kyiv raion outlines and every marker. */}
        {zoneLayerOn && (
          <>
            <AlertZoneLayer />
            <ZoneAutoFit />
          </>
        )}
        {/* Real OSM raion boundaries with hover name tooltips; clicks bubble
            through to the map (pan / home placement). */}
        <DistrictLayer />
        {/* City-wide pulse layer over the inert base boundaries. Per-incident
            raion "attack heat" (IncidentHighlight) is intentionally not drawn. */}
        <CitywidePulse />

        {/* Distance reference for the whole map. Metric only, and bottom-RIGHT
            because the bottom-left corner belongs to MapControls. */}
        <ScaleControl position="bottomright" imperial={false} maxWidth={110} />

        <ResizeHandler />
        <HomeController />
        <InspectController />

        {/* Hidden while arming a new position — HomePlacement shows the single
            house being placed (cursor ghost / center pin) instead. */}
        {home && !placingHome && (
          <>
            {/* Keyed by danger level: setStyle doesn't re-apply className, so
                the pulse class only attaches on a fresh mount (same trick as
                CitywidePulse's color-keyed GeoJSON). */}
            <Circle
              key={`home-${danger}`}
              center={[home.lat, home.lon]}
              radius={home.radiusKm * 1000}
              pathOptions={{
                color: homeCircleColor,
                fillColor: homeCircleColor,
                fillOpacity: danger === "none" ? 0.06 : 0.14,
                weight: danger === "none" ? 1 : 2,
                className: danger === "danger" ? "home-danger-pulse" : undefined,
              }}
            />
            <Marker
              position={[home.lat, home.lon]}
              icon={homeIcon(homeStyle.icon, homeCircleColor, homeStyle.glow)}
            >
              <Tooltip direction="top" offset={[0, -18]}>
                {t("legend.home")} · {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
              </Tooltip>
            </Marker>
          </>
        )}

        {/* Shared homes of friends (markers only — no radius, no danger). */}
        <FriendLayer />

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
      <HomeCompass map={map} />
      <HomePlacement map={map} />
      <MapControls />
    </div>
  );
}
