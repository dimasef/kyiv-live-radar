import L from "leaflet";
import { memo, useMemo } from "react";
import { CircleMarker, Marker, Polyline } from "react-leaflet";

import { threatState } from "../../threatDisplay";
import { threatColor } from "../../theme";
import { DIRECTIONAL, DOT_UNTIL_MOVING, threatDivIcon } from "../../threatIcons";
import type { Threat } from "../../types";
import { KYIV_PT } from "./constants";
import ThreatPopup from "./ThreatPopup";
import { hasMovement, headingOf, inboundHeading, trackPoints } from "./track";

/** Two expanding rings pulsing in the threat color — the live head of a track. */
function pulseIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: "pulse-wrap",
    html:
      `<span class="pulse-ring" style="--c:${color}"></span>` +
      `<span class="pulse-ring pulse-ring--slow" style="--c:${color}"></span>`,
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
}: {
  threat: Threat;
  highlighted?: boolean;
}) {
  const pts = trackPoints(threat);
  const color = threatColor(threat);
  // Only a track that actually moved over time gets a heading/vector — a single
  // multi-district message is an enumeration, not a trajectory (see hasMovement).
  // An impact is a POINT strike, never a trajectory: it must NEVER draw a
  // connecting vector even when re-reports give it several timestamps (a
  // ballistic can't "move" between districts) — so kind='impact' is excluded.
  const moved = threat.kind !== "impact" && hasMovement(threat);
  const realHeading = moved ? headingOf(threat) : null;
  const type = threat.target_type;
  // A drone sighted as a single point still flies toward Kyiv — aim its glyph
  // inbound rather than a meaningless due-north. Missiles stay a fix dot until
  // they truly move, so exclude DOT_UNTIL_MOVING types.
  const last = pts.length > 0 ? pts[pts.length - 1] : null;
  const presumedHeading =
    realHeading == null && last != null && DIRECTIONAL[type] && !DOT_UNTIL_MOVING[type]
      ? inboundHeading(last, KYIV_PT, threat.id)
      : null;
  const heading = realHeading ?? presumedHeading;

  // Head-marker state: influences SHAPE. A hit bursts; a shot-down/lost track is
  // struck through; a moving track points along its heading. A cruise missile
  // with no heading yet is an honest dot (DOT_UNTIL_MOVING); drones and
  // ballistic/unknown show their glyph from the first sighting (a drone points
  // up until it gains a course, then rotates along the vector).
  const state = threatState(threat, { heading, directional: DOT_UNTIL_MOVING[type] });

  const pulse = useMemo(() => pulseIcon(color), [color]);
  const headIcon = useMemo(
    () =>
      threatDivIcon(type, {
        state,
        bearingDeg: heading ?? 0,
        color,
        size: highlighted ? 30 : 26,
      }),
    [type, state, heading, color, highlighted],
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
  const dim = 0.5 + 0.5 * Math.max(0, Math.min(1, threat.confidence));
  const corroborated = threat.corroboration_count >= 2;

  return (
    <>
      {moved && latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity flips.
          key={`${threat.id}-${active ? "live" : "closed"}-${highlighted ? "insp" : ""}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight: highlighted ? 5 : 3,
            opacity: (active ? 0.8 : highlighted ? 0.75 : 0.45) * dim,
            className:
              [active && "track-flow", highlighted && "track-inspect"].filter(Boolean).join(" ") ||
              undefined,
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
      {/* Pulsing rings on the live head of an active track. */}
      {active && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulse}
          interactive={false}
          zIndexOffset={-100}
        />
      )}
      <Marker position={[head.lat, head.lon]} icon={headIcon} opacity={dim}>
        <ThreatPopup threat={threat} />
      </Marker>
    </>
  );
});

export default ThreatLayer;
