import { useEffect } from "react";
import { useMap } from "react-leaflet";

import { useRadar } from "@/store";

/** Esc drops the current target selection: the popup closes and the track stops
 * being the inspected one.
 *
 * Both halves, because they are one act. Picking a card in the feed highlights
 * the track, flies to it and opens its popup — so dismissing only the popup
 * left the map still holding a target the operator had finished with, and the
 * feed card still lit. `InspectController` documents a click into the map as
 * the only way out of a selection; this is that gesture on the keyboard.
 *
 * Leaflet's own Esc-closes-popup never reaches this. Its Keyboard handler binds
 * the key hooks only while the map container holds focus
 * (`map.on('focus', addHooks)`), and a selection made in the feed leaves focus
 * on the feed card — which is also why this listens at the document rather than
 * on the container: the selection is an app-level state made from either side
 * of the screen.
 *
 * Layering under the other surfaces that answer Esc: Overlay and
 * RegroupPickBanner listen at window CAPTURE and stop the event, so it never
 * arrives here while one of those is up. The settings drawer does not — it
 * listens in the bubble phase like this does — so it is checked by name, and a
 * typing surface owns its own Esc (clearing a search box must not also clear
 * the map).
 */
export default function SelectionEscape() {
  const map = useMap();
  const active = useRadar((s) => s.openPopupThreatId != null || s.inspectedThreat != null);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      const state = useRadar.getState();
      if (state.settingsOpen || isTyping(e.target)) return;
      // Popup first: clearing the selection can unmount the layer that owns it,
      // and Leaflet should be the one taking its own DOM down.
      map.closePopup();
      state.clearInspection();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [map, active]);

  return null;
}

/** Whether the keypress belongs to a field being typed into — Esc there means
 * "clear what I am writing", not "drop the target I am reading". */
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  const tag = el?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable === true;
}
