import { useEffect } from "react";
import { Marker } from "react-leaflet";

import { canSeeImpacts } from "@/api";
import { useRadar } from "@/store";
import { IMPACT_REFRESH_MS } from "@/store/impactsSlice";
import { MARKER_PX } from "@/store/prefsSlice";
import { threatDivIcon } from "@/threatIcons";

import ThreatPopup from "./ThreatPopup";
import { trackPoints } from "./track";

/** Where strikes landed, for the accounts an operator has vouched for.
 *
 * Every other live surface withholds this (see the backend's IMPACT_ROLES): a
 * "hit in Дарницький" published while the raid is still running is damage
 * assessment for whoever launched it. So this layer is off by default, asks for
 * nothing until it is switched on, and is the only place in the app that draws
 * an impact before the alert is over.
 *
 * Points, never trails: an impact is where something arrived, and threatVisual
 * already refuses it a vector. It reuses the burst glyph the journal and the
 * feed already use for `status: 'impact'`, so a strike looks the same wherever
 * it is shown. */
export default function ImpactLayer() {
  const on = useRadar((s) => s.impactLayerOn);
  const impacts = useRadar((s) => s.impacts);
  const refresh = useRadar((s) => s.refreshImpacts);
  const markerSize = useRadar((s) => s.mapMarkerSize);
  // Part of the effect's key, not just a guard: the switch is remembered across
  // reloads while the session hydrates asynchronously, so at boot the first
  // attempt runs before the role is known. Without this the layer sat empty
  // until the next tick a minute later.
  const allowed = useRadar((s) => canSeeImpacts(s.user?.role));

  // A timer is genuinely outside React, and impacts have no websocket to ride:
  // the server never broadcasts one, on purpose.
  useEffect(() => {
    if (!on || !allowed) return;
    refresh();
    const id = setInterval(refresh, IMPACT_REFRESH_MS);
    return () => clearInterval(id);
  }, [on, allowed, refresh]);

  if (!on) return null;

  return (
    <>
      {impacts.map((impact) => {
        const pts = trackPoints(impact);
        const at = pts[pts.length - 1];
        if (!at) return null;
        return (
          <Marker
            key={impact.id}
            position={[at.lat, at.lon]}
            icon={threatDivIcon(impact.target_type, {
              state: "impact",
              size: MARKER_PX[markerSize],
              count: impact.target_count,
              seed: impact.id,
            })}
          >
            <ThreatPopup threat={impact} />
          </Marker>
        );
      })}
    </>
  );
}
