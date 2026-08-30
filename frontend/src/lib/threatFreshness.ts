import type { Threat } from '@/types'

/** How stale a target is, and how much that should dim it on the map.
 *
 * Our targets always move. One that hasn't been re-sighted in ten minutes is
 * almost certainly not there any more — but until now it looked exactly as
 * convincing as a target confirmed seconds ago, and then a «Чисто»/«Дорозвідка»
 * wiped dozens of them off the map at once. Fading makes a target's age visible,
 * so the picture degrades gradually instead of jumping.
 *
 * The clock the fade runs against is the SERVER's: every threat carries
 * `stale_at`, the exact instant the sweeper will auto-close it, computed with the
 * per-type window (5 min for a district ballistic, 20 otherwise). Nothing about
 * that rule is duplicated here — change it on the backend and the fade follows.
 */

/** Hold full brightness for this share of the window: a target seen a moment ago
 * is not suspicious, and fading from t=0 would make everything look uncertain. */
const FADE_START = 0.35

/** «Затихла» — past halfway to its own auto-close. Where the live cues (pulse,
 * flowing vector) switch off and the popup starts naming the age in words. */
const QUIET_AT = 0.5

/** Floor, never 0: the sweeper runs on a 60 s tick, so a target can sit past its
 * window while still formally active — it must stay visible (and clickable)
 * until the server actually closes it. */
const MIN_FADE = 0.25

/** An inspected target never dims below this — the operator's attention wins. */
const INSPECTED_FLOOR = 0.85

/** Fallback stale window when the payload predates the freshness fields (a
 * service-worker-cached bundle talking to an older API). Mirrors the backend
 * default `track_stale_minutes`; the real value always comes from `stale_at`. */
const FALLBACK_WINDOW_MS = 20 * 60 * 1000

const HAS_ZONE = /(?:Z|z|[+-]\d{2}:?\d{2})$/

/** Parse an API timestamp, treating a zone-less one as UTC.
 *
 * `Date.parse` reads an ISO string without an offset as LOCAL time, so one
 * missing 'Z' silently shifts every age by the viewer's UTC offset — a Kyiv
 * client once showed "186 хв тому" for a 6-minute-old sighting (+3 h). The
 * server is the real fix (see api/serialize.py::_utc); this makes the class of
 * bug impossible to reintroduce quietly, since every stored timestamp is UTC.
 */
function parseUtc(iso: string | null | undefined): number {
  if (!iso) return NaN
  return Date.parse(HAS_ZONE.test(iso) ? iso : `${iso}Z`)
}

/** Last-seen time of a track: the server's `last_event_at`, else the newest
 * event we hold, else when the track was created. */
export function lastSeenMs(threat: Threat): number {
  const published = parseUtc(threat.last_event_at)
  if (!Number.isNaN(published)) return published
  let t = parseUtc(threat.created_at)
  for (const ev of threat.events) {
    const e = parseUtc(ev.event_time)
    if (!Number.isNaN(e) && e > t) t = e
  }
  return t
}

/** When the server will consider this target stale and close it. */
function staleAtMs(threat: Threat): number {
  const published = parseUtc(threat.stale_at)
  if (!Number.isNaN(published)) return published
  return lastSeenMs(threat) + FALLBACK_WINDOW_MS
}

/** How far a target has travelled toward its own auto-close: 0 = just seen,
 * 1 = due to be closed. Can exceed 1 while the sweeper catches up. */
export function stalePhase(threat: Threat, now: number): number {
  const seen = lastSeenMs(threat)
  const span = staleAtMs(threat) - seen
  if (!Number.isFinite(span) || span <= 0) return 0
  return Math.max(0, (now - seen) / span)
}

function smoothstep(x: number): number {
  const t = Math.max(0, Math.min(1, x))
  return t * t * (3 - 2 * t)
}

/** Opacity multiplier for every layer of a target: 1 while fresh, easing down to
 * MIN_FADE as its auto-close arrives.
 *
 * Impacts never fade — a strike is a historical fact, not a target that could
 * have moved on. A track closed by NEWS (збито, відбій, «чисто») doesn't fade
 * here either: something was actually reported about it, so it stays legible for
 * its linger and its disappearance is animated in CSS (`.threat-icon--closing`).
 *
 * The exception is `closed_reason: 'stale'`, which is the absence of news — the
 * sweeper retiring a target nobody has mentioned. Exempting it too meant a track
 * that had spent minutes dimming to MIN_FADE snapped back to FULL brightness at
 * the instant it was closed (the marker ~4x, the vector ~2x), sat there for the
 * whole linger, and only then left: the quietest thing on the map became the
 * loudest, right when the map was saying the opposite. Its phase keeps growing
 * past 1, so it simply stays at the floor it had already reached. */
export function fadeFactor(threat: Threat, now: number, inspected = false): number {
  if (threat.kind === 'impact') return 1
  if (threat.closed_at && threat.closed_reason !== 'stale') return 1
  const p = stalePhase(threat, now)
  if (p <= FADE_START) return 1
  const decay = smoothstep((p - FADE_START) / (1 - FADE_START))
  const faded = 1 - (1 - MIN_FADE) * decay
  return inspected ? Math.max(faded, INSPECTED_FLOOR) : faded
}

/** True once nobody has reported this target for over half its stale window. */
export function isQuiet(threat: Threat, now: number): boolean {
  if (threat.kind === 'impact' || threat.closed_at) return false
  return stalePhase(threat, now) >= QUIET_AT
}

/** Whether a target should show the LIVE cues — the pulse rings, the flowing
 * vector, the glyph's idle drift.
 *
 * They all answer one question ("is anyone still reporting this?"), so they
 * share one rule: motion means live, stillness means the reports stopped. A
 * closed track and an impact are never live — an impact especially, since it is
 * a recorded strike location and must sit exactly where it is.
 *
 * Note this is NOT `!isQuiet`: that returns false for closed tracks and impacts
 * too (nothing to call quiet), which read back as "live" if simply negated. */
export function showsLiveMotion(threat: Threat, now: number): boolean {
  if (threat.kind === 'impact' || threat.closed_at) return false
  return !isQuiet(threat, now)
}

/** Whole minutes since a target was last reported (floored, never negative). */
export function minutesSinceSeen(threat: Threat, now: number): number {
  return Math.max(0, Math.floor((now - lastSeenMs(threat)) / 60_000))
}
