import { useEffect, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";

import { centerPinMode } from "@/lib/device";
import { useRadar } from "@/store";

/** Handles map clicks (set home) and auto-recenters when geolocation resolves. */
export default function HomeController() {
  const map = useMap();
  const home = useRadar((s) => s.home);
  const setHome = useRadar((s) => s.setHome);
  const flown = useRef(false);
  // A home that already existed at mount (persisted, origin 'geo') must NOT
  // trigger the fly-to: that replayed a world->home zoom arc on every app
  // open. Only a geolocation fix that lands DURING the session recenters.
  const initialHome = useRef(useRadar.getState().home);

  useMapEvents({
    click(e) {
      const state = useRadar.getState();
      // Only place home when the user explicitly armed placement — otherwise a
      // click is just a map interaction and must not move home.
      if (!state.placingHome) return;
      // On touch, placement is confirmed via the center pin + button
      // (HomePlacement); a tap fires this same click event, so ignore it here —
      // otherwise the tap would drop home before the user aimed the pin.
      if (centerPinMode()) return;
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
    if (home?.origin === "geo" && !flown.current && home !== initialHome.current) {
      map.flyTo([home.lat, home.lon], 12);
      flown.current = true;
    }
  }, [home, map]);

  return null;
}
