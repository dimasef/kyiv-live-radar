import L from "leaflet";

import { fixDotSvg, threatGlyphSvg } from "@/threatIcons";
import type { ThreatState } from "@/threatIcons";
import type { TargetType } from "@/types";

// Split out of threatIcons.ts (2026-09-12): a bare `import L from 'leaflet'`
// at that file's top pulled Leaflet's whole engine — with its side effects
// Rollup can't prove absent — into every consumer, including the feed row and
// notification prefs that never touch the map. Only this divIcon builder
// needs Leaflet itself; keeping it here means it ships only in the map's own
// (lazy-loaded) chunk.

interface IconOpts {
  state?: ThreatState;
  bearingDeg?: number;
  color?: string;
  size?: number;
  /** Stated group size. Spotters count targets constantly ("3 на Славутич"), and
   * a group of six used to look exactly like a single drone on the map — the
   * number was only in the popup and the feed. */
  count?: number | null;
  /** The track just closed and is living out its linger — the icon fades away
   * over it instead of blinking out. A «Чисто» closes dozens of tracks in one
   * message, and dozens of markers vanishing on the same frame read as a glitch
   * rather than as an all-clear. */
  closing?: boolean;
  /** Give the glyph its idle drift: a ~1px circular wander that says the contact
   * is live. It is deliberately CIRCULAR and sub-pixel-slow — a target's
   * position must never appear to change, and any straight-line motion would be
   * read as heading, which the glyph's rotation already means. Same condition as
   * the pulse rings (active and not quiet), so a target that stops being
   * reported goes still. */
  drift?: boolean;
  /** Track id, used only to stagger the drift phase. Without it every marker
   * orbits in lockstep and the whole map appears to wobble as one. */
  seed?: number;
}

/** Leaflet divIcon для мапи. Колір передається ззовні (тип, або сірий якщо збито). */
export function threatDivIcon(type: TargetType, opts: IconOpts = {}): L.DivIcon {
  const {
    state = "active", bearingDeg = 0, color, size = 26, closing = false, count,
    drift = false, seed = 0,
  } = opts;
  const raw =
    state === "fix"
      ? fixDotSvg(size, color)
      : threatGlyphSvg(type, { size, state, bearingDeg, color });
  // Wrapped, never applied to the marker root: Leaflet owns that element's
  // transform (it is how the marker is positioned), so animating it there would
  // fight the map on every pan. The bearing rotation lives INSIDE the svg, so
  // the wrapper's transform is free.
  const glyph = drift
    ? `<span class="threat-drift" style="animation-delay:-${(seed % 36) / 10}s">${raw}</span>`
    : raw;
  // Deliberately a SIBLING of the svg, never inside it: the glyph is rotated to
  // the movement heading, and a number inside that transform would hang upside
  // down on a southbound target. Neutral colours (never the type colour — a
  // yellow numeral on the yellow shahed glyph is unreadable), and
  // pointer-events:none so it can't swallow the click that opens the popup.
  const badge =
    count != null && count > 1 ? `<span class="threat-count">×${count}</span>` : "";
  return L.divIcon({
    html: glyph + badge,
    // без дефолтних стилів leaflet
    className: closing ? "threat-icon threat-icon--closing" : "threat-icon",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}
