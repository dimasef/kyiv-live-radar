import L from "leaflet";
import { Marker, Popup } from "react-leaflet";

import { currentRegion } from "@/lib/regions";
import { useRadar } from "@/store";
import { isInFeed, isPinnedRegion } from "@/store/feedRegions";
import type { RegionInfo } from "@/types";

import { badgeLabel, badgeStateOf, badgeSvg } from "./regionBadge";
import RegionMenu from "./RegionMenu";

/** The drawn chip. */
const BADGE_SIZE = 26;
/** The element around it — the tap target. A finger needs ~40 px, but a 40 px
 * chip at zoom 6 would cover a small oblast; the extra is transparent padding
 * that `.region-badge` centres the glyph inside. */
const BADGE_HIT = 40;

/** A tappable state chip at each oblast's centre — the touch-screen half of this
 * layer.
 *
 * The desktop affordance for all of this is a hover, and a finger has none: on a
 * phone the outlines only changed shade, with nothing to say why or that they
 * could be tapped at all. The badge is that missing half. It also gives the
 * gesture a target: the polygon fill is still tappable, but an oblast at zoom 6
 * is a shape you have to aim at, and its neighbours are one thumb-width away.
 */
export default function RegionBadges({ regions }: { regions: RegionInfo[] }) {
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions);
  const followed = useRadar((s) => currentRegion(s));

  return (
    <>
      {regions.map((region) => {
        const state = badgeStateOf({
          isHome: isPinnedRegion(region.id, followed),
          inFeed: isInFeed(region.id, feedExtraRegions, followed),
        });
        const label = `${region.name_uk} — ${badgeLabel(state)}`;
        return (
          <Marker
            key={`${region.id}-${state}`}
            position={[region.center_lat, region.center_lon]}
            icon={L.divIcon({
              html: badgeSvg(state, BADGE_SIZE),
              className: "region-badge",
              iconSize: [BADGE_HIT, BADGE_HIT],
              iconAnchor: [BADGE_HIT / 2, BADGE_HIT / 2],
            })}
            eventHandlers={{
              add: (e) => e.target.getElement()?.setAttribute("aria-label", label),
            }}
            zIndexOffset={-200}
          >
            <Popup>
              <RegionMenu region={region} />
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}
