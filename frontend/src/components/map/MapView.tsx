import L from "leaflet";
import { useMemo, useState } from "react";
import { MapContainer, ScaleControl, TileLayer } from "react-leaflet";

import { homeStyleOf } from "@/lib/contactMarker";
import { framingBounds } from "@/lib/regions";
import { homeDangerFor, raionIdsForZone } from "@/lib/homeDanger";
import { useRadar } from "@/store";
import AdminTrackEditor from "./AdminTrackEditor";
import AlertZoneLayer from "./AlertZoneLayer";
import AxisLayer from "./AxisLayer";
import CitywidePulse from "./CitywidePulse";
import {
  BASEMAP_URL,
  MIN_ZOOM,
  MOTION_BUDGET,
  UKRAINE_BOUNDS,
  WORLD_BOUNDS,
} from "./constants";
import {
  HomeController,
  InspectController,
  ResizeHandler,
  ZoneAutoFit,
} from "./controllers";
import DistrictLayer from "./DistrictLayer";
import ImpactLayer from "./ImpactLayer";
import FriendLayer from "./FriendLayer";
import HomeCompass from "./HomeCompass";
import HomeMarker from "./HomeMarker";
import HomePlacement from "./HomePlacement";
import MapControls from "./MapControls";
import RegionLayer from "./RegionLayer";
import RegroupPickBanner from "./RegroupPickBanner";
import ThreatLayer from "./ThreatLayer";
import { useMapViewport } from "./useMapViewport";
import { isVisible } from "./viewportCull";

export default function MapView() {
  const threats = useRadar((s) => s.threats);
  const boundaries = useRadar((s) => s.boundaries);
  const home = useRadar((s) => s.home);
  const homeStyle = homeStyleOf(useRadar((s) => s.homeStyle));
  const placingHome = useRadar((s) => s.placingHome);
  const inspectedThreat = useRadar((s) => s.inspectedThreat);
  const zoneLayerOn = useRadar((s) => s.zoneLayerOn);
  const [map, setMap] = useState<L.Map | null>(null);
  const regions = useRadar((s) => s.regions);
  // A class rather than a prop threaded through every layer: the map's other
  // animations (the city-wide breath, the home-danger ring) live in CSS and
  // belong to components that have no reason to know about a setting.
  const mapMotion = useRadar((s) => s.mapMotion);
  const chosenRegion = useRadar((s) => s.chosenRegion);

  // What the map frames: the region the reader follows, or the whole country
  // until one is known. Derived every render rather than read once at mount —
  // the catalogue arrives AFTER first paint, so a mount-time read could only
  // ever see the fallback, and a reader on Сумщина opened on Kyiv every reload.
  //
  // Re-deriving it is safe because ResizeHandler owns the actual fitting and
  // only re-fits when this VALUE changes (the catalogue landing, or the reader
  // picking another region) — never over a view they panned themselves.
  const framing = useMemo(
    () => framingBounds(regions, chosenRegion, UKRAINE_BOUNDS),
    [regions, chosenRegion],
  );

  // A track being inspected might already be live (in `threats`) — in that
  // case the live copy has fresher data, so just highlight it in place rather
  // than rendering a second, stale layer on top of it.
  const inspectedIsLive = inspectedThreat != null && inspectedThreat.id in threats;

  // Only what the operator can actually see gets handed to Leaflet. Every open
  // track used to be drawn and animated regardless of where the view was
  // pointing: at the 2026-08-21 peak that was 113 tracks and ~380 continuous
  // animations to show maybe a dozen. Null viewport = the map hasn't reported
  // one yet, which must mean "draw everything", never "draw nothing".
  //
  // Two tracks are exempt, both for the same reason — the operator is reading
  // them: the inspected one (its card may be open while the map looks
  // elsewhere) and whichever has its popup open. Culling the second would tear
  // the popup off the screen mid-sentence, and its close event would then let
  // the store evict the track outright.
  const view = useMapViewport(map);
  const openPopupThreatId = useRadar((s) => s.openPopupThreatId);
  // Third exemption, same reason: while an admin is picking a new track for a
  // sighting, the track it came FROM has to stay on screen — they are looking
  // at it to decide where it belongs.
  const pickSourceId = useRadar((s) => s.regroupPick?.sourceThreatId);
  const shown = useMemo(() => {
    const all = Object.values(threats);
    if (!view) return all;
    return all.filter(
      (th) =>
        th.id === inspectedThreat?.id ||
        th.id === openPopupThreatId ||
        th.id === pickSourceId ||
        isVisible(th, view),
    );
  }, [threats, view, inspectedThreat?.id, openPopupThreatId, pickSourceId]);

  // Counted over what is DRAWN, not what is open — with culling in front of it,
  // a quiet corner of a busy night keeps its motion (see MOTION_BUDGET).
  const overBudget = shown.length > MOTION_BUDGET;

  // 25 point-in-polygon tests over every raion boundary, and it depends only
  // on the home zone — without this it re-ran on every live frame, which during
  // a raid is dozens of times a minute.
  const homeRaionIds = useMemo(
    () => (home ? raionIdsForZone(home, boundaries) : []),
    [home, boundaries],
  );
  // Deliberately the FULL set, not `shown`: a target closing on the home raion
  // is exactly the one worth warning about while the map is looking elsewhere.
  // Culling decides what is drawn, never what is known.
  const danger = home ? homeDangerFor(threats, home, homeRaionIds) : "none";

  return (
    <div className={`relative h-full w-full ${mapMotion ? "" : "motion-off"}`}>
      <MapContainer
        ref={setMap}
        bounds={framing}
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
        {/* Oblast outlines + the menu that adds a region to the feed. Only
            drawn zoomed out past the raion layer, and unmounted while home
            placement is armed so its popup can never eat that click. */}
        {!placingHome && <RegionLayer />}
        {/* Real OSM raion boundaries with hover name tooltips; clicks bubble
            through to the map (pan / home placement). */}
        <DistrictLayer />
        {/* City-wide pulse layer over the inert base boundaries. Per-incident
            raion "attack heat" (IncidentHighlight) is intentionally not drawn. */}
        <CitywidePulse />

        {/* Distance reference for the whole map. Metric only, and bottom-RIGHT
            because the bottom-left corner belongs to MapControls. */}
        <ScaleControl position="bottomright" imperial={false} maxWidth={110} />

        <ResizeHandler bounds={framing} />
        <HomeController />
        <InspectController />

        {/* Hidden while arming a new position — HomePlacement shows the single
            house being placed (cursor ghost / center pin) instead. */}
        {home && !placingHome && (
          <HomeMarker home={home} homeStyle={homeStyle} danger={danger} />
        )}

        {/* Shared homes of friends (markers only — no radius, no danger). */}
        <FriendLayer />

        {/* Strike locations — role-gated, off by default, its own request. */}
        <ImpactLayer />

        {shown.map((th) => (
          <ThreatLayer
            key={th.id}
            threat={th}
            highlighted={inspectedThreat?.id === th.id}
            lean={overBudget}
          />
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
      {/* Both live OUTSIDE MapContainer: the editor must survive the marker
          that opened it being removed from the map (see AdminTrackEditor). */}
      <RegroupPickBanner />
      <AdminTrackEditor />
    </div>
  );
}
