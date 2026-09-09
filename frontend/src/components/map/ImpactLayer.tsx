import { useEffect } from "react";
import { Marker } from "react-leaflet";

import { aftermathDivIcon } from "@/aftermathIcons";
import { canSeeImpacts } from "@/api";
import { fadeFactor } from "@/lib/aftermathFreshness";
import { useRadar } from "@/store";
import { IMPACT_REFRESH_MS } from "@/store/impactsSlice";
import { MARKER_PX } from "@/store/prefsSlice";
import { threatDivIcon } from "@/threatIcons";

import AftermathPopup from "./AftermathPopup";
import ImpactPopup from "./ImpactPopup";
import { trackPoints } from "./track";

/** What this night did to these streets, for the accounts an operator has
 * vouched for: confirmed hits AND what a strike did to a raion — fires, damage,
 * casualties, rescue work.
 *
 * Every other live surface withholds both (see the backend's IMPACT_ROLES): a
 * "hit in Дарницький" published while the raid is still running is damage
 * assessment for whoever launched it, and «горить багатоповерхівка в
 * Дарницькому» is the same assessment by another route. So this layer is off by
 * default, is fetched only for the accounts allowed to see it, and is the only
 * place in the app that draws either before the alert is over.
 *
 * One layer, one toggle, two marker sets, because the reader is asking one
 * question and the two answers differ only in whether anyone confirmed the hit
 * itself. Both are the same yellow ring, and only size tells them apart: an
 * impact is the full-size ring whatever fell (the type is a chip in its popup,
 * never a silhouette on the map), a consequence a smaller one whatever it did
 * (the categories are chips in its popup) that fades with its own age. What is
 * still in the air outranks what already happened.
 *
 * Points, never trails: an impact is where something arrived, and threatVisual
 * already refuses it a vector. A report is a raion, not a path. */
export default function ImpactLayer() {
  const on = useRadar((s) => s.impactLayerOn);
  const impacts = useRadar((s) => s.impacts);
  const aftermath = useRadar((s) => s.aftermath);
  const refresh = useRadar((s) => s.refreshImpacts);
  const markerSize = useRadar((s) => s.mapMarkerSize);
  const now = useRadar((s) => s.nowMs + s.clockSkewMs);
  // The effect's key, not just a guard: the session hydrates asynchronously,
  // so at boot the first attempt runs before the role is known. Without this
  // the layer sat empty until the next tick a minute later.
  const allowed = useRadar((s) => canSeeImpacts(s.user?.role));

  // A timer is genuinely outside React, and impacts have no websocket to ride:
  // the server never broadcasts one, on purpose. Runs while the layer is OFF
  // too — the button's badge counts what is under it before it is pressed.
  useEffect(() => {
    if (!allowed) return;
    refresh();
    const id = setInterval(refresh, IMPACT_REFRESH_MS);
    return () => clearInterval(id);
  }, [allowed, refresh]);

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
            <ImpactPopup threat={impact} />
          </Marker>
        );
      })}

      {aftermath.map((report) => {
        if (report.lat == null || report.lon == null) return null;
        return (
          <Marker
            key={`a${report.id}`}
            position={[report.lat, report.lon]}
            // Smaller than a target marker by design: it must be findable
            // without competing with anything still flying.
            icon={aftermathDivIcon({ size: Math.round(MARKER_PX[markerSize] * 0.8) })}
            opacity={fadeFactor(report, now)}
          >
            <AftermathPopup report={report} />
          </Marker>
        );
      })}
    </>
  );
}
