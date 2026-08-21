import type { RawMessage } from "@/types";

// Same condition as OutcomeBadge's tone: a real ThreatEvent/Notice matched,
// i.e. this message actually became a card in the main feed (ThreatLog) —
// not just a best-effort "outcome" guess.
export function inMainFeed(item: RawMessage) {
  return item.events.length > 0 || item.notice_id != null;
}

/** Left-border tint: green = became a sighting, blue = became a notice only,
 * near-invisible = the parser surfaced nothing from it. */
export function rowBorderClass(item: RawMessage) {
  if (!inMainFeed(item)) return "border-white/[0.05]";
  return item.events.length > 0 ? "border-emerald-400/40" : "border-sky-400/40";
}
