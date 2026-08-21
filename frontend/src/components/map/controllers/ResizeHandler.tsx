import { useEffect } from "react";
import { useMap } from "react-leaflet";

import { observeResize } from "@/lib/observers";

import { KYIV_BOUNDS } from "../constants";

/** Keeps Leaflet's cached container size in sync with the real DOM box.
 *
 * On mobile the map often mounts before its container has settled to full
 * height (dynamic viewport bar, bottom-sheet layout, PWA safe-area insets), so
 * Leaflet captures a too-short size and tiles render in a thin strip until the
 * user navigates away and back (which remounts at the correct size). A
 * ResizeObserver on the actual container calls invalidateSize() whenever the
 * box changes — first paint, orientation change, sheet reflow — so it always
 * self-corrects. */
export default function ResizeHandler() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    // The initial KYIV_BOUNDS fit runs against whatever box the map mounted
    // with — on mobile that's often a near-zero height (dynamic viewport bar,
    // PWA insets), which resolves to a WORLD-level zoom. So after every size
    // settle, re-fit the Kyiv overview — until the view changes for any other
    // reason (user gesture or a programmatic flyTo), which must not be
    // snapped back.
    let viewTaken = false;
    let refitting = false;
    const markTaken = () => {
      if (!refitting) viewTaken = true;
    };
    map.on("zoomstart", markTaken);
    map.on("dragstart", markTaken);

    // Fire once after mount in case the container was already resized before the
    // observer attached (ResizeObserver only reports changes after subscribing,
    // but implementations deliver an initial callback — belt-and-suspenders).
    const kick = () => {
      map.invalidateSize({ animate: false });
      if (!viewTaken) {
        refitting = true;
        map.fitBounds(KYIV_BOUNDS, { padding: [20, 20], animate: false });
        refitting = false;
      }
    };
    const raf = requestAnimationFrame(kick);

    const stopResizeObserver = observeResize(container, kick);
    // Mobile Safari fires these without a corresponding element resize.
    window.addEventListener("orientationchange", kick);
    window.addEventListener("pageshow", kick);

    return () => {
      cancelAnimationFrame(raf);
      stopResizeObserver();
      map.off("zoomstart", markTaken);
      map.off("dragstart", markTaken);
      window.removeEventListener("orientationchange", kick);
      window.removeEventListener("pageshow", kick);
    };
  }, [map]);

  return null;
}
