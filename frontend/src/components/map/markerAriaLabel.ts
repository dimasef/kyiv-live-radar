import { threatChip } from "@/threatLabels";
import { typeLabel } from "@/threatState";
import type { Threat } from "@/types";

// Leaflet marks every clickable marker keyboard-focusable with role="button"
// (Marker's default `keyboard: true`) but never gives it a name — divIcon
// markers get no `alt` the way plain L.Icon <img>s do. Same wording the popup
// and feed chip already use (threatChip), so a screen reader and a sighted
// reader hear/see the same thing.
export function threatAriaLabel(threat: Threat, t: (key: string) => string): string {
  const type = typeLabel(threat, t) ?? t("target.unknown");
  const { labelKey } = threatChip(threat);
  return `${type}, ${t(labelKey)}`;
}
