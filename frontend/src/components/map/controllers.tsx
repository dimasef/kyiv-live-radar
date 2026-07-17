import { useEffect, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";

import { useRadar } from "../../store";
import { trackPoints } from "./track";

/** Keeps Leaflet's cached container size in sync with the real DOM box.
 *
 * On mobile the map often mounts before its container has settled to full
 * height (dynamic viewport bar, bottom-sheet layout, PWA safe-area insets), so
 * Leaflet captures a too-short size and tiles render in a thin strip until the
 * user navigates away and back (which remounts at the correct size). A
 * ResizeObserver on the actual container calls invalidateSize() whenever the
 * box changes — first paint, orientation change, sheet reflow — so it always
 * self-corrects. */
export function ResizeHandler() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    // Fire once after mount in case the container was already resized before the
    // observer attached (ResizeObserver only reports changes after subscribing,
    // but implementations deliver an initial callback — belt-and-suspenders).
    const kick = () => map.invalidateSize({ animate: false });
    const raf = requestAnimationFrame(kick);

    const ro = new ResizeObserver(kick);
    ro.observe(container);
    // Mobile Safari fires these without a corresponding element resize.
    window.addEventListener("orientationchange", kick);
    window.addEventListener("pageshow", kick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("orientationchange", kick);
      window.removeEventListener("pageshow", kick);
    };
  }, [map]);

  return null;
}

/** Handles map clicks (set home) and auto-recenters when geolocation resolves. */
export function HomeController() {
  const map = useMap();
  const home = useRadar((s) => s.home);
  const setHome = useRadar((s) => s.setHome);
  const flown = useRef(false);

  useMapEvents({
    click(e) {
      const state = useRadar.getState();
      // Only place home when the user explicitly armed placement — otherwise a
      // click is just a map interaction and must not move home.
      if (!state.placingHome) return;
      setHome({
        lat: e.latlng.lat,
        lon: e.latlng.lng,
        radiusKm: state.home?.radiusKm ?? 3,
        origin: "manual",
      });
      state.setPlacingHome(false);
    },
  });

  useEffect(() => {
    if (home?.origin === "geo" && !flown.current) {
      map.flyTo([home.lat, home.lon], 12);
      flown.current = true;
    }
  }, [home, map]);

  return null;
}

/** Flies the map to fit an inspected track the moment its points arrive —
 * once per selection, not on every subsequent event update. */
export function InspectController() {
  const map = useMap();
  const inspected = useRadar((s) => s.inspectedThreat);
  const liveThreats = useRadar((s) => s.threats);
  const fittedId = useRef<number | null>(null);

  useEffect(() => {
    if (!inspected) return;
    if (fittedId.current === inspected.id) return;
    // Prefer the live copy so an already-open track's points (and thus the
    // fly-to) are available instantly, instead of waiting on our own fetch.
    const display = liveThreats[inspected.id] ?? inspected;
    const pts = trackPoints(display);
    if (pts.length === 0) return;
    fittedId.current = inspected.id;
    if (pts.length === 1) {
      map.flyTo([pts[0].lat, pts[0].lon], 13);
    } else {
      map.flyToBounds(
        pts.map((p) => [p.lat, p.lon] as [number, number]),
        { padding: [56, 56], maxZoom: 14 },
      );
    }
  }, [inspected, liveThreats, map]);

  return null;
}
