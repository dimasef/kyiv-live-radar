import L from "leaflet";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Marker, Tooltip, useMap, useMapEvents } from "react-leaflet";

import { contactMarkerSvg, contactStyleOf, type ContactStyle } from "@/lib/contactMarker";
import { navigate, userPath } from "@/router";
import { useRadar } from "@/store";
import { spreadOverlapping, type Offsets, type PixelPoint } from "./spreadMarkers";

const SIZE = 22;
const HALF = SIZE / 2;
const OWN_HOME_ID = "me";

// One divIcon per (icon, colour, offset) triple; cached so a re-render doesn't
// rebuild identical markers. The offset is part of the key because it lives in
// iconAnchor — see below.
const iconCache = new Map<string, L.DivIcon>();
function markerIcon(style: ContactStyle, [dx, dy]: [number, number]): L.DivIcon {
  const { icon, color, glow } = style;
  const key = `${icon}|${color}|${glow}|${dx},${dy}`;
  let divIcon = iconCache.get(key);
  if (!divIcon) {
    divIcon = L.divIcon({
      className: "friend-marker",
      html: contactMarkerSvg(icon, color, SIZE, glow),
      iconSize: [SIZE, SIZE],
      // Leaflet draws the icon so that iconAnchor lands on the marker's latlng,
      // so pulling the anchor back by (dx, dy) pushes the DRAWING that far
      // without touching the coordinates the marker actually stands for.
      iconAnchor: [HALF - dx, HALF - dy],
    });
    iconCache.set(key, divIcon);
  }
  return divIcon;
}

/** Where every home marker lands on screen right now, so overlaps can be
 * detected in the units they actually happen in — pixels. Metres won't do: two
 * homes 40 m apart overlap when zoomed out and are far apart when zoomed in. */
function useHomeOffsets(homes: { id: string; lat: number; lon: number }[]): Offsets {
  const map = useMap();
  const [, bumpOnZoom] = useState(0);
  // Zoom changes the pixel distance between fixed coordinates, so the layout
  // has to be recomputed. A Leaflet event is genuinely outside React, which is
  // what this subscription is for.
  useMapEvents({ zoomend: () => bumpOnZoom((n) => n + 1) });

  const points: PixelPoint[] = homes.map((h) => {
    const p = map.latLngToLayerPoint([h.lat, h.lon]);
    return { id: h.id, x: p.x, y: p.y };
  });
  return spreadOverlapping(points, { minGap: SIZE + 4, anchorId: OWN_HOME_ID });
}

/** Markers for every contact who shares a home (the server only sends `home`
 * for those — see friends_routes._friend_out) AND that the user hasn't hidden
 * on their own map. Each uses the contact's chosen colour + icon.
 *
 * The user's own home is fed into the layout too (though drawn by MapView): a
 * contact living in the same building used to render straight on top of it. */
export default function FriendLayer() {
  const { t } = useTranslation();
  const friends = useRadar((s) => s.friends);
  const hiddenHomeIds = useRadar((s) => s.hiddenHomeIds);
  const contactStyles = useRadar((s) => s.contactStyles);
  const ownHome = useRadar((s) => s.home);

  const visible = friends.filter((f) => f.home != null && !hiddenHomeIds.includes(f.id));
  const offsets = useHomeOffsets([
    ...(ownHome ? [{ id: OWN_HOME_ID, lat: ownHome.lat, lon: ownHome.lon }] : []),
    ...visible.map((f) => ({ id: String(f.id), lat: f.home!.lat, lon: f.home!.lon })),
  ]);

  return (
    <>
      {visible.map((f) => {
        const style = contactStyleOf(contactStyles[f.id]);
        const [dx, dy] = offsets.get(String(f.id)) ?? [0, 0];
        return (
          <Marker
            key={f.id}
            position={[f.home!.lat, f.home!.lon]}
            icon={markerIcon(style, [dx, dy])}
            // A marker is the only place a contact appears outside the account
            // page, so it's the natural way in to who they are.
            eventHandlers={{ click: () => navigate(userPath(f.id)) }}
          >
            <Tooltip direction="top" offset={[dx, dy - 14]}>
              {f.display_name || f.email || t("friends.friend")}
            </Tooltip>
          </Marker>
        );
      })}
    </>
  );
}
