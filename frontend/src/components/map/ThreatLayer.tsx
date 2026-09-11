import L from "leaflet";
import { memo, useEffect, useMemo, useRef } from "react";
import { CircleMarker, Marker, Polyline, useMap } from "react-leaflet";

import { fadeFactor, showsLiveMotion } from "@/lib/threatFreshness";
import { useRadar } from "@/store";
import { MARKER_PX } from "@/store/prefsSlice";

import { HOME_DANGER_COLORS } from "@/theme";
import { threatDivIcon } from "@/threatIcons";
import type { Threat } from "@/types";
import ThreatPopup from "./ThreatPopup";
import { threatVisual } from "./threatVisual";

/** --phosphor, the app's accent — spelled out because this is a Leaflet path
 * option, not a class. */
const PICK_COLOR = "#22d3ee";

/** Two expanding rings pulsing in the threat color — the live head of a track.
 * One ring under the motion budget: the second exists to make a lone contact
 * read as breathing, and it is the first thing worth spending when the map is
 * carrying a crowd (see MOTION_BUDGET). */
function pulseIcon(color: string, lean: boolean): L.DivIcon {
  const ring = `<span class="pulse-ring" style="--c:${color}"></span>`;
  return L.divIcon({
    className: "pulse-wrap",
    html: lean
      ? ring
      : ring + `<span class="pulse-ring pulse-ring--slow" style="--c:${color}"></span>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });
}

// Memoized so a new event on ONE track doesn't re-render every OTHER track's
// layer too — react-leaflet calls marker.setIcon() whenever the `icon` prop
// object changes identity, which makes Leaflet tear down and recreate the
// marker's DOM (the pulse-ring spans, the arrow svg), restarting their CSS
// keyframe animations from 0%. Unrelated markers would visibly "pop" back in
// on every unrelated update. Icons are additionally useMemo'd so even a
// re-render of THIS track's own layer reuses the same icon object when color
// and heading haven't actually changed.
const ThreatLayer = memo(function ThreatLayer({
  threat,
  highlighted = false,
  lean = false,
  dangerTriggerEventId = null,
}: {
  threat: Threat;
  highlighted?: boolean;
  /** The sighting that put the home at DANGER, when it is this track's. Drawn
   * as its own marker if it is not the head — an echo channel's fix near home
   * while the narrator's path is elsewhere. A primitive, so the memo holds. */
  dangerTriggerEventId?: number | null;
  /** The map is over MOTION_BUDGET: keep every shape, drop the motion. The
   * inspected track is exempt — it is the one the operator is reading. */
  lean?: boolean;
}) {
  // Ticks every 10s (clockSlice), corrected for a wrong device clock. Selected
  // as a primitive right here rather than passed down from MapView, so the tick
  // re-renders only the threat layers and not every other map layer.
  const now = useRadar((s) => s.nowMs + s.clockSkewMs);
  // Only the store decides when a track is actually leaving — never derived from
  // closed_at here. The inspected copy is closed too, and is meant to stay put
  // for as long as the operator wants it (store/threatsSlice), so deriving the
  // exit fade from closed_at made a clicked-on target dissolve while being read.
  const leaving = useRadar((s) => s.leavingThreatIds.includes(threat.id));
  const setOpenPopupThreat = useRadar((s) => s.setOpenPopupThreat);
  // Regrouping a sighting by picking its new track off the map: while that is
  // armed, every OTHER target is a destination rather than something to read.
  const regroupPick = useRadar((s) => s.regroupPick);
  const completeRegroupPick = useRadar((s) => s.completeRegroupPick);
  // Reader's map settings. Selected as primitives, so changing one re-renders
  // the threat layers and nothing else.
  const showTrail = useRadar((s) => s.mapTrail);
  const trackWidth = useRadar((s) => s.mapTrackWidth);
  const markerSize = useRadar((s) => s.mapMarkerSize);
  const motion = useRadar((s) => s.mapMotion);
  // The trail setting quietens the DEFAULT view only. Asking about one target
  // is the moment its path becomes the answer, so the inspected track and the
  // one with its popup open keep theirs either way: this is about the map being
  // quiet at rest, never about withholding a track's history from someone who
  // just clicked it.
  const popupOpen = useRadar((s) => s.openPopupThreatId === threat.id);
  const trail = showTrail || highlighted || popupOpen;
  const trailWeight = trackWidth + (highlighted ? 2 : 0);
  const pickable = regroupPick != null && regroupPick.sourceThreatId !== threat.id;
  const map = useMap();
  const markerRef = useRef<L.Marker | null>(null);
  const type = threat.target_type;
  const { pts, echoPts, color, moved, heading, state } = threatVisual(threat);

  // Motion is spent on the inspected track no matter how busy the map is — but
  // a reader who switched motion off means it, inspected track included.
  const still = !motion || (lean && !highlighted);
  const pulse = useMemo(() => pulseIcon(color, still), [color, still]);
  // Computed before the early returns below so the hook order stays fixed — the
  // icon needs it, and it depends on the ticking clock.
  const live = showsLiveMotion(threat, now);
  const headIcon = useMemo(
    () =>
      threatDivIcon(type, {
        state,
        bearingDeg: heading ?? 0,
        color,
        // +4 for the inspected one, whatever size the reader picked.
        size: MARKER_PX[markerSize] + (highlighted ? 4 : 0),
        closing: leaving,
        count: threat.target_count,
        drift: live && !still,
        seed: threat.id,
      }),
    [type, state, heading, color, highlighted, leaving, threat.target_count, threat.id, live,
     still, markerSize],
  );

  // Picking a target in the feed opens its popup too — the click already means
  // "tell me about this one", and making the operator find the marker and click
  // it again to read what they just asked for is a step for nothing.
  //
  // AFTER the fly-to lands, never during it: a popup's autoPan calls
  // `_panAnim.stop()` on open (Leaflet's Popup._adjustPan), so opening one
  // mid-flight kills InspectController's flight and leaves the map wherever it
  // had got to. `moveend` is that landing, and every fresh selection flies —
  // including one that ends where it started, since flyTo fires the event
  // either way. A track with no points never flies and never renders a marker
  // here, so the two agree by construction.
  //
  // This does lean on the flight being ASYNC, which is where it degrades: on an
  // engine without 3d transforms (the TV browser) flyTo falls straight through
  // to setView, whose `moveend` has already fired by the time this effect runs
  // — InspectController is mounted above these layers, so its effect goes
  // first. There the popup simply does not auto-open, which is what the map did
  // before this existed. Worth knowing before "fixing" it by opening eagerly:
  // that trades a missing convenience for a map that stops mid-flight.
  //
  // Opened a tick AFTER `moveend`, never inside it. That event is not only the
  // landing: ANOTHER popup's autoPan fires it too, synchronously, when it stops
  // a flight in progress (Popup._adjustPan → _panAnim.stop()). Opening ours in
  // that same call closed the other popup while Leaflet was still halfway
  // through positioning it, and it crashed on its now-null map — «Радар
  // зламався» on a phone, 2026-09-11. A macrotask lets the other popup finish
  // before it is closed.
  useEffect(() => {
    if (!highlighted || pickable) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const open = () => {
      timer = setTimeout(() => {
        const marker = markerRef.current;
        if (marker && !marker.isPopupOpen()) marker.openPopup();
      }, 0);
    };
    map.once("moveend", open);
    return () => {
      map.off("moveend", open);
      clearTimeout(timer);
    };
  }, [highlighted, pickable, map]);

  if (pts.length === 0) return null;
  // City-wide threats have no real location (their event sits on the city-centre
  // sentinel) — they're shown as a banner, not a map point. Skip rendering here.
  if (threat.scope === "city") return null;

  const latlngs = pts.map((p) => [p.lat, p.lon] as [number, number]);
  const head = pts[pts.length - 1];
  const trigger =
    dangerTriggerEventId != null
      ? (threat.events.find((ev) => ev.id === dangerTriggerEventId) ?? null)
      : null;
  const triggerPt =
    trigger && trigger.lat != null && trigger.lon != null &&
    (trigger.lat !== head.lat || trigger.lon !== head.lon)
      ? { lat: trigger.lat, lon: trigger.lon }
      : null;
  const active = !threat.closed_at;
  // Confidence is a VISUAL WEIGHT, not just popup text: a one-source guess reads
  // fainter than a multi-source confirmation. Floor at 0.5 so a low-confidence
  // marker is still legible. corroboration >= 2 adds a halo ring — real weight.
  // Age multiplies on top: our targets always move, so one nobody has re-reported
  // in a while has almost certainly moved on, and it fades out as its server-side
  // auto-close approaches (see lib/threatFreshness).
  const dim =
    (0.5 + 0.5 * Math.max(0, Math.min(1, threat.confidence))) *
    fadeFactor(threat, now, highlighted);
  const corroborated = threat.corroboration_count >= 2;

  return (
    <>
      {trail && moved && latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity (or
          // going quiet, which drops the flow animation) flips.
          key={`${threat.id}-${active ? "live" : "closed"}-${live ? "" : "quiet"}-${highlighted ? "insp" : ""}-${still ? "still" : ""}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight: trailWeight,
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
            dashArray: !active && threat.has_conflict ? "6 6" : undefined,
          }}
        />
      )}
      {trail &&
        pts.slice(0, -1).map((p, i) => (
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
      {/* Echo dots: a fix still valid now reads solid, one that has aged out
          reads faint — "where the other channels saw it just now" versus
          "where they saw it earlier". */}
      {(highlighted || popupOpen) &&
        echoPts.map((p, i) => {
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
      {triggerPt && (
        <CircleMarker
          center={[triggerPt.lat, triggerPt.lon]}
          radius={highlighted ? 9 : 7}
          interactive={false}
          pathOptions={{
            color: HOME_DANGER_COLORS.danger,
            weight: 2,
            opacity: 0.95,
            fillColor: HOME_DANGER_COLORS.danger,
            fillOpacity: 0.35,
          }}
        />
      )}
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
      {/* Pulsing rings on the live head of an active track — off once it goes
          quiet, so "pulsing" always means "someone is still reporting this". */}
      {live && motion && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulse}
          interactive={false}
          zIndexOffset={-100}
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
      <Marker
        ref={markerRef}
        position={[head.lat, head.lon]}
        icon={headIcon}
        opacity={dim}
        // A closed target's popup is exactly what someone reads right after
        // "мінус" — while it's open the store holds off the eviction.
        eventHandlers={
          pickable
            ? { click: () => void completeRegroupPick(threat.id).catch(() => {}) }
            : {
                popupopen: () => setOpenPopupThreat(threat.id),
                popupclose: () => setOpenPopupThreat(null),
              }
        }
      >
        {/* No Popup child while picking: react-leaflet binds the popup by its
            presence, and an auto-opening popup would swallow the pick click. */}
        {!pickable && <ThreatPopup threat={threat} />}
      </Marker>
    </>
  );
});

export default ThreatLayer;
