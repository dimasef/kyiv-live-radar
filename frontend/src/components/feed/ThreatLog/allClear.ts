import type { Alert, Notice, Region } from "@/types";

/** How far an all-clear notice may sit from an official alert's end and still
 * be talking about it. A spotter types «Відбій» when they see the sirens stop,
 * which is minutes either side of the moment the official channel posts it. */
const MATCH_TOLERANCE_MS = 10 * 60_000;

/** The official city alert this all-clear closed, or null.
 *
 * Only a FULL clear is matched. A type-scoped stand-down («Відбій балістичної
 * загрози») ends one kind of threat while the raid keeps running — labelling it
 * with the alert's duration would tell the reader the тривога is over when it
 * is not, which is the one thing this card must never do.
 *
 * Only the SAME region's alert, too. Matching on time alone would let a
 * northern spotter's «Відбій», typed within the tolerance below of Kyiv's
 * siren ending, be stamped with Kyiv's duration — an alert that never covered
 * the reader, presented as the one that just ended over them. Unreachable
 * while Kyiv is the only region with an alert channel, which is exactly why it
 * would have gone unnoticed; the region column (backend migration 0036) is
 * what lets it be closed before it is reachable rather than after.
 *
 * Nearest end wins, not newest: on a night with two alerts an hour apart, the
 * notice belongs to whichever one it sits beside.
 */
export function alertForClear(
  alerts: Alert[],
  notice: Notice,
  home: Region = "kyiv",
): Alert | null {
  if (notice.target_type !== "unknown") return null;
  const region = notice.region ?? home;
  const at = new Date(notice.event_time).getTime();
  let best: Alert | null = null;
  let bestGap = Infinity;
  for (const a of alerts) {
    if (a.scope !== "city" || a.region !== region || !a.ended_at) continue;
    const gap = Math.abs(new Date(a.ended_at).getTime() - at);
    if (gap <= MATCH_TOLERANCE_MS && gap < bestGap) {
      best = a;
      bestGap = gap;
    }
  }
  return best;
}

/** The ways the all-clear card finishes its sentence. Keys, not strings — the
 * card is bilingual, and the tail has to travel with the rest of it. */
export const CLEAR_TAILS = [
  "notice.clearTail1",
  "notice.clearTail2",
  "notice.clearTail3",
  "notice.clearTail4",
] as const;

/** Which tail this notice gets.
 *
 * Derived from the notice id, NOT Math.random(): this card re-renders on every
 * store change, and during a raid that is several times a second — a random
 * pick would have the sentence flickering between three wordings while someone
 * reads it. Keyed on the id it is chosen once, stays chosen through every
 * re-render and every reload, and still varies from one відбій to the next,
 * which is the part that was actually wanted. It also means two people looking
 * at the same alert read the same sentence.
 */
export function clearTailKey(noticeId: number): string {
  // Scaled from the TOP bits, not `% length`: this hash's low bits stay
  // correlated for small inputs, and taking them straight put seven of the
  // eight most recent real all-clears on the same wording.
  return CLEAR_TAILS[
    Math.floor((scatter(noticeId) / 2 ** 32) * CLEAR_TAILS.length)
  ];
}

/** Spreads consecutive ids across the 32-bit range (murmur3's finalizer).
 *
 * A bare `id % 4` looked fine and wasn't: the official channel's all-clears sit
 * at a stride that shares a factor with the tail count, so four of the eight
 * most recent ones landed on the same wording. Hashing first breaks that
 * alignment for any number of tails, and stays fully deterministic. */
function scatter(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  return (h ^ (h >>> 16)) >>> 0;
}
