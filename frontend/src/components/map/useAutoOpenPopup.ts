import L from "leaflet";
import type { RefObject } from "react";
import { useEffect } from "react";

/** Two expanding rings pulsing in the threat color — the live head of a track.
 * One ring under the motion budget: the second exists to make a lone contact
 * read as breathing, and it is the first thing worth spending when the map is
 * carrying a crowd (see MOTION_BUDGET). */
export function pulseIcon(color: string, lean: boolean): L.DivIcon {
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
export function useAutoOpenPopup({
  map,
  markerRef,
  enabled,
}: {
  map: L.Map;
  markerRef: RefObject<L.Marker | null>;
  enabled: boolean;
}): void {
  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled, map, markerRef]);
}
