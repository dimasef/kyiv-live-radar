import L from "leaflet";
import { useTranslation } from "react-i18next";
import { Marker, Tooltip } from "react-leaflet";

import { contactMarkerSvg, contactStyleOf } from "../../lib/contactMarker";
import { useRadar } from "../../store";

// One divIcon per (icon, colour) pair the user has chosen; cached so a
// re-render doesn't rebuild identical markers.
const iconCache = new Map<string, L.DivIcon>();
function markerIcon(icon: string, color: string): L.DivIcon {
  const key = `${icon}|${color}`;
  let divIcon = iconCache.get(key);
  if (!divIcon) {
    divIcon = L.divIcon({
      className: "friend-marker",
      html: contactMarkerSvg(icon, color, 22),
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
    iconCache.set(key, divIcon);
  }
  return divIcon;
}

/** Markers for every contact who shares a home (the server only sends `home`
 * for those — see friends_routes._friend_out) AND that the user hasn't hidden
 * on their own map. Each uses the contact's chosen colour + icon (local pref). */
export default function FriendLayer() {
  const { t } = useTranslation();
  const friends = useRadar((s) => s.friends);
  const hiddenHomeIds = useRadar((s) => s.hiddenHomeIds);
  const contactStyles = useRadar((s) => s.contactStyles);

  return (
    <>
      {friends
        .filter((f) => f.home != null && !hiddenHomeIds.includes(f.id))
        .map((f) => {
          const { icon, color } = contactStyleOf(contactStyles[f.id]);
          return (
            <Marker key={f.id} position={[f.home!.lat, f.home!.lon]} icon={markerIcon(icon, color)}>
              <Tooltip direction="top" offset={[0, -14]}>
                {f.display_name || f.email || t("friends.friend")}
              </Tooltip>
            </Marker>
          );
        })}
    </>
  );
}
