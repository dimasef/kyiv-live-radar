import { hasMovement, trackPoints } from "@/components/map/track";
import { bearing, haversineKm, type Pt } from "@/lib/geo";
import { HOME_DANGER } from "@/lib/homeDanger";
import type { Home } from "@/store/homeSlice";
import type { Threat, ThreatEvent } from "@/types";

/** Below this the two readings are the same distance as far as a district
 * centroid can tell — calling that "closing" would be noise. */
const TREND_DEADBAND_KM = 1;

export interface HomeDistance {
  /** Km from home to the target's current position. Approximate by nature:
   * every sighting is a district/landmark centroid, not a fix. */
  km: number;
  /** Compass bearing home -> target, for the direction arrow. */
  bearingFromHome: number;
  /** Whether the last leg of the track moved toward or away from home; null
   * for a single-point sighting (no trajectory to read). */
  trend: "closing" | "receding" | null;
  /** Inside the home zone plus the same buffer home-danger uses. */
  nearHome: boolean;
}

/** How far the target is from home right now, or null if that can't be said.
 *
 * Uses only the LATEST sighting cluster, like homeDanger: one message can name
 * several districts, and where the target IS is the newest of them — the
 * nearest, so the number never understates how close it got. */
export function homeDistanceOf(threat: Threat, home: Home): HomeDistance | null {
  // A city-wide threat has no position; a distance to it would be invented.
  if (threat.scope === "city") return null;
  const located = threat.events.filter((ev) => ev.lat != null && ev.lon != null);
  if (located.length === 0) return null;

  const latest = located.reduce((max, ev) => (ev.event_time > max ? ev.event_time : max), "");
  let nearest: Pt | null = null;
  let km = Infinity;
  for (const ev of located) {
    if (ev.event_time !== latest) continue;
    const p = { lat: ev.lat!, lon: ev.lon! };
    const d = haversineKm(p, home);
    if (d < km) {
      km = d;
      nearest = p;
    }
  }
  if (nearest == null) return null;

  return {
    km,
    bearingFromHome: bearing(home, nearest),
    trend: trendOf(threat, home),
    nearHome: km <= home.radiusKm + HOME_DANGER.bufferKm,
  };
}

/** What ONE sighting says about its own distance from home.
 *
 * The feed's reading, as against `homeDistanceOf`'s. A feed row is about a place
 * a spotter named at a moment; the track it belongs to has since moved on, and
 * measuring the track there gave every row of one track the SAME number — five
 * cards reading «~18 км» over Боярка, Теремки, Жуляни and Голосіїв, which are
 * nowhere near 18 km from each other (reported 2026-08-31). The card already
 * draws this distinction for its count badge, which shows the count known AS OF
 * the event rather than the track's final one.
 *
 * Event-local by necessity as well as by meaning: `/events/recent` serves feed
 * rows through `threat_out_shallow`, whose `events` is always `[]`, so anything
 * derived from the track is absent there — which is why the badge used to
 * disappear on a page reload.
 *
 * No trend: one sighting is a point, and a trajectory needs two.
 */
export function sightingDistanceOf(
  event: Pick<ThreatEvent, "lat" | "lon">,
  home: Home,
): Omit<HomeDistance, "trend"> | null {
  if (event.lat == null || event.lon == null) return null;
  const p = { lat: event.lat, lon: event.lon };
  const km = haversineKm(p, home);
  return {
    km,
    bearingFromHome: bearing(home, p),
    nearHome: km <= home.radiusKm + HOME_DANGER.bufferKm,
  };
}

function trendOf(threat: Threat, home: Home): "closing" | "receding" | null {
  // A destroyed/lost/closed track isn't going anywhere, and an impact is a
  // place, not a movement — "віддаляється" about either reads as a live target
  // still in the air.
  if (threat.closed_at != null || threat.kind === "impact") return null;
  if (!hasMovement(threat)) return null;
  const pts = trackPoints(threat);
  if (pts.length < 2) return null;
  const delta = haversineKm(pts[pts.length - 1], home) - haversineKm(pts[pts.length - 2], home);
  if (Math.abs(delta) < TREND_DEADBAND_KM) return null;
  return delta < 0 ? "closing" : "receding";
}
