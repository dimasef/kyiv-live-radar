import type L from "leaflet";
import { memo, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Marker, useMap } from "react-leaflet";

import { fadeFactor, showsLiveMotion } from "@/lib/threatFreshness";
import { useRadar } from "@/store";
import { MARKER_PX } from "@/store/prefsSlice";

import type { Threat } from "@/types";
import { threatAriaLabel } from "./markerAriaLabel";
import { threatDivIcon } from "./threatDivIcon";
import ThreatEchoDots from "./ThreatEchoDots";
import ThreatHeadRings from "./ThreatHeadRings";
import ThreatPopup from "./ThreatPopup";
import ThreatTrail from "./ThreatTrail";
import { threatVisual } from "./threatVisual";
import { pulseIcon, useAutoOpenPopup } from "./useAutoOpenPopup";

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
  const { t } = useTranslation();
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
  const clearInspection = useRadar((s) => s.clearInspection);
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
  // Set by InspectController the moment it flies here; this layer opens the
  // popup when that flight lands.
  const armedToOpen = useRadar((s) => s.pendingPopupThreatId === threat.id);
  const disarmPopupOpen = useRadar((s) => s.disarmPopupOpen);
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

  useAutoOpenPopup({ map, markerRef, enabled: armedToOpen && !pickable, disarm: disarmPopupOpen });

  /** Closing the popup with its × means "done with this target", so the feed
   * card stops being lit too — the same single act that Esc performs
   * (SelectionEscape) and that a click into the map performs
   * (InspectController). Only the × used to stop halfway.
   *
   * Guarded, because the app closes popups of its own accord and those closes
   * must NOT deselect: picking another target closes the previous popup while
   * the new one is already the inspected track, and arming a regroup pick
   * unmounts every other target's popup. Both are excluded by asking who is
   * inspected RIGHT NOW rather than trusting the `highlighted` prop — the
   * handler's closure can still be the one from before the selection changed,
   * since InspectController's effect runs ahead of this layer's re-binding. */
  const dropSelectionIfMine = () => {
    const state = useRadar.getState();
    if (state.regroupPick == null && state.inspectedThreat?.id === threat.id) {
      clearInspection();
    }
  };

  // Leaflet makes every clickable marker keyboard-focusable (role="button")
  // but never names it — a divIcon gets no `alt` the way an <img> icon would.
  // Imperative, not an `icon` option: setIcon() reuses this same DOM node (see
  // the memo comment above threatDivIcon's useMemo), so the label must be
  // re-applied whenever the wording actually changes rather than set once.
  const ariaLabel = threatAriaLabel(threat, t);
  useEffect(() => {
    markerRef.current?.getElement()?.setAttribute("aria-label", ariaLabel);
  }, [ariaLabel]);

  if (pts.length === 0) return null;
  // City-wide threats have no real location (their event sits on the city-centre
  // sentinel) — they're shown as a banner, not a map point. Skip rendering here.
  if (threat.scope === "city") return null;

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
      {trail && (
        <ThreatTrail
          pts={pts}
          color={color}
          weight={trailWeight}
          dim={dim}
          active={active}
          live={live}
          highlighted={highlighted}
          leaving={leaving}
          still={still}
          moved={moved}
          hasConflict={threat.has_conflict}
        />
      )}
      {(highlighted || popupOpen) && (
        <ThreatEchoDots echoPts={echoPts} color={color} dim={dim} now={now} />
      )}
      <ThreatHeadRings
        head={head}
        highlighted={highlighted}
        color={color}
        dim={dim}
        corroborated={corroborated}
        pickable={pickable}
      />
      {/* Pulsing rings on the live head of an active track — off once it goes
          quiet, so "pulsing" always means "someone is still reporting this". */}
      {live && motion && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulse}
          interactive={false}
          // `interactive` only skips pointer/click handling — Leaflet's
          // tabindex+role="button" is gated by the SEPARATE `keyboard` option
          // (default true), so a purely decorative marker needs this too or
          // it is still a nameless, do-nothing stop on the tab order.
          keyboard={false}
          zIndexOffset={-100}
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
                popupclose: () => {
                  setOpenPopupThreat(null);
                  dropSelectionIfMine();
                },
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
