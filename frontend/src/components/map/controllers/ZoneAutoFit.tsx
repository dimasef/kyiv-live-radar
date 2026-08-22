import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

import { useRadar } from "@/store";

import { zoneFitBounds } from "../alertZones";
import { ZONE_FIT_PADDING } from "../constants";

/** Widens the view to take in every raion the alert layer lights up, once per
 * switch-on.
 *
 * Switching the layer on at the Kyiv default framing used to draw most of it
 * off-screen: the watched area reaches past Чернігів to the Belarus border,
 * roughly three times the box the map opens at, so the operator turned on a
 * layer and saw two raions of it.
 *
 * It only ever ZOOMS OUT. The target box is unioned with what is already on
 * screen, and a box already inside the view moves nothing at all — a map being
 * watched during a raid must not yank itself away from the target the operator
 * is following just because a siren came on somewhere else.
 *
 * The polygons load lazily on that same switch, so the fit cannot happen in the
 * store action that starts the fetch: this waits for the geometry to land (the
 * effect re-runs when it does) and then answers the request by token. */
export default function ZoneAutoFit() {
  const map = useMap();
  const token = useRadar((s) => s.zoneFitToken);
  const geometry = useRadar((s) => s.zoneGeometry);
  const answered = useRef(0);

  useEffect(() => {
    if (token === 0 || answered.current === token) return;
    // Read rather than subscribe: the siren state is polled every 20 s, and
    // this component has no reason to re-render on a frame it will ignore.
    const bounds = zoneFitBounds(geometry, useRadar.getState().zones);
    if (!bounds) return;
    answered.current = token;
    const lit = L.latLngBounds(bounds);
    if (map.getBounds().contains(lit)) return;
    map.flyToBounds(lit.extend(map.getBounds()), { padding: ZONE_FIT_PADDING });
  }, [map, token, geometry]);

  return null;
}
