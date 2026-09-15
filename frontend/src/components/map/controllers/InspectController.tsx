import { useEffect, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";

import { useRadar } from "@/store";

import { INSPECT_MAX_ZOOM, INSPECT_ZOOM } from "../constants";
import { trackPoints } from "../track";

/** Flies the map to fit an inspected track the moment its points arrive —
 * once per selection, not on every subsequent event update — and drops the
 * selection on a click into the map.
 *
 * That click is the only way out: the feed card that made the selection can be
 * scrolled out of reach (on mobile the sheet collapses the moment you pick a
 * target). Leaflet bubbles clicks to the map from paths — districts, the home
 * circle — but NOT from markers, so opening a target's popup is not a
 * deselection. */
export default function InspectController() {
  const map = useMap();
  const inspected = useRadar((s) => s.inspectedThreat);
  // Narrow on purpose: subscribing to the whole `threats` map re-ran this
  // effect on every live frame, for a component that only ever reads ONE track.
  const liveCopy = useRadar((s) => (inspected ? s.threats[inspected.id] : undefined));
  const armPopupOpen = useRadar((s) => s.armPopupOpen);
  const disarmPopupOpen = useRadar((s) => s.disarmPopupOpen);
  const fittedId = useRef<number | null>(null);

  useMapEvents({
    click() {
      const state = useRadar.getState();
      // While arming a home, the click belongs to placement (HomeController).
      if (state.placingHome || !state.inspectedThreat) return;
      state.clearInspection();
    },
  });

  useEffect(() => {
    if (!inspected) {
      // Re-selecting the same track after a deselect should fly to it again.
      fittedId.current = null;
      disarmPopupOpen();
      return;
    }
    if (fittedId.current === inspected.id) return;
    // Prefer the live copy so an already-open track's points (and thus the
    // fly-to) are available instantly, instead of waiting on our own fetch.
    const display = liveCopy ?? inspected;
    const pts = trackPoints(display);
    if (pts.length === 0) return;
    fittedId.current = inspected.id;
    // Whatever popup is open belongs to the PREVIOUS selection, and an open
    // popup is a hazard for the flight: its marker may move on the next live
    // frame, and a moving popup autoPans, which stops the animation halfway.
    // The new selection's popup opens on landing (ThreatLayer).
    map.closePopup();
    // Armed here rather than wherever the selection changed: the popup opens on
    // the landing of THIS flight, and only a flight that is about to start can
    // promise one. See useAutoOpenPopup.
    armPopupOpen(inspected.id);
    if (pts.length === 1) {
      // Never zoom IN past INSPECT_ZOOM, but don't zoom the operator OUT if
      // they're already closer — just recenter at their current zoom.
      map.flyTo([pts[0].lat, pts[0].lon], Math.max(INSPECT_ZOOM, map.getZoom()));
    } else {
      map.flyToBounds(
        pts.map((p) => [p.lat, p.lon] as [number, number]),
        { padding: [56, 56], maxZoom: INSPECT_MAX_ZOOM },
      );
    }
  }, [inspected, liveCopy, map, armPopupOpen, disarmPopupOpen]);

  return null;
}
