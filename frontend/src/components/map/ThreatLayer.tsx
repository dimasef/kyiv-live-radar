import L from "leaflet";
import { memo, useMemo } from "react";
import { CircleMarker, Marker, Polyline } from "react-leaflet";

import { fadeFactor, showsLiveMotion } from "@/lib/threatFreshness";
import { useRadar } from "@/store";

import { threatDivIcon } from "@/threatIcons";
import type { Threat } from "@/types";
import ThreatPopup from "./ThreatPopup";
import { threatVisual } from "./threatVisual";

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
}: {
  threat: Threat;
  highlighted?: boolean;
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
  const type = threat.target_type;
  const { pts, color, moved, heading, state } = threatVisual(threat);

  // Motion is spent on the inspected track no matter how busy the map is.
  const still = lean && !highlighted;
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
        size: highlighted ? 30 : 26,
        closing: leaving,
        count: threat.target_count,
        drift: live && !still,
        seed: threat.id,
      }),
    [type, state, heading, color, highlighted, leaving, threat.target_count, threat.id, live, still],
  );

  if (pts.length === 0) return null;
  // City-wide threats have no real location (their event sits on the city-centre
  // sentinel) — they're shown as a banner, not a map point. Skip rendering here.
  if (threat.scope === "city") return null;

  const latlngs = pts.map((p) => [p.lat, p.lon] as [number, number]);
  const head = pts[pts.length - 1];
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
      {moved && latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity (or
          // going quiet, which drops the flow animation) flips.
          key={`${threat.id}-${active ? "live" : "closed"}-${live ? "" : "quiet"}-${highlighted ? "insp" : ""}-${still ? "still" : ""}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight: highlighted ? 5 : 3,
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
      {live && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulse}
          interactive={false}
          zIndexOffset={-100}
        />
      )}
      <Marker
        position={[head.lat, head.lon]}
        icon={headIcon}
        opacity={dim}
        // A closed target's popup is exactly what someone reads right after
        // "мінус" — while it's open the store holds off the eviction.
        eventHandlers={{
          popupopen: () => setOpenPopupThreat(threat.id),
          popupclose: () => setOpenPopupThreat(null),
        }}
      >
        <ThreatPopup threat={threat} />
      </Marker>
    </>
  );
});

export default ThreatLayer;
