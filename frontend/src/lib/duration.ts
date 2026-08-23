/** Just enough of i18next's `t` to format one duration. A structural type, so
 * this file stays free of the i18n dependency and the tests can pass a stub. */
type Translate = (key: string, vars: Record<string, number>) => string;

/** How long something ran, in the reader's language ("1 год 47 хв" / "1h 47m").
 *
 * Reuses the `zones.*` duration strings rather than minting feed-specific ones:
 * the raion-alert layer already had to say exactly this in both languages, and
 * two copies of a format string is how one of them ends up untranslated — which
 * is what happened to the attack summary, hardcoded to Ukrainian units.
 *
 * Rounds UP to a minute at the bottom: an alert that lasted forty seconds still
 * lasted, and "0 хв" reads as a bug rather than as brevity. */
export function durationLabel(
  t: Translate,
  startedAt: string,
  endedAt: string,
): string {
  const mins = Math.max(
    1,
    Math.round(
      (new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 60000,
    ),
  );
  if (mins < 60) return t("zones.m", { m: mins });
  return t("zones.hm", { h: Math.floor(mins / 60), m: mins % 60 });
}
