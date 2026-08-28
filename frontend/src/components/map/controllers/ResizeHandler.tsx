import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

import { observeResize } from "@/lib/observers";


/** Keeps Leaflet's cached container size in sync with the real DOM box.
 *
 * On mobile the map often mounts before its container has settled to full
 * height (dynamic viewport bar, bottom-sheet layout, PWA safe-area insets), so
 * Leaflet captures a too-short size and tiles render in a thin strip until the
 * user navigates away and back (which remounts at the correct size). A
 * ResizeObserver on the actual container calls invalidateSize() whenever the
 * box changes — first paint, orientation change, sheet reflow — so it always
 * self-corrects. */
export default function ResizeHandler({
  bounds,
}: {
  bounds: [[number, number], [number, number]];
}) {
  const map = useMap();
  // Depended on by value, not by identity: an array literal would be a new
  // object every render and snap the view back on each one. MapView memoizes
  // it, and this key makes that a guarantee rather than a convention.
  const key = bounds.flat().join(",");
  // Held in a ref so the effect depends on the VALUE (via `key`) and not on the
  // array's identity — `exhaustive-deps` is an error in this project, and
  // silencing it here would silence the real thing it is guarding.
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;

  useEffect(() => {
    const container = map.getContainer();
    // Leaflet's initial fit runs against whatever box the map mounted with — on
    // mobile that's often a near-zero height (dynamic viewport bar, PWA
    // insets), which resolves to a WORLD-level zoom. So after every size
    // settle, re-fit the current framing — until the view changes for any other
    // reason (user gesture or a programmatic flyTo), which must not be
    // snapped back.
    //
    // Re-running on `key` is the OTHER half of the job: `bounds` changing means
    // the thing being framed changed (the region catalogue landed, or the
    // reader chose another oblast), and that always deserves a fit — including
    // over a view they had panned, because they just asked to look elsewhere.
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
        map.fitBounds(boundsRef.current, { padding: [20, 20], animate: false });
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
  }, [map, key]);

  return null;
}
