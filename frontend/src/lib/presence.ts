/** Buckets a last-seen timestamp for display. Deliberately coarse past the
 * first hour: the exact minute of someone's night is more than the feature
 * needs to answer ("are they around?"), and the label has to fit a list row. */
export type PresenceLabel =
  | { kind: 'online' }
  | { kind: 'never' }
  | { kind: 'minutes'; value: number }
  | { kind: 'hours'; value: number }
  | { kind: 'days'; value: number }

export function presenceLabel(
  { online, lastSeenAt }: { online: boolean; lastSeenAt: string | null | undefined },
  now: number = Date.now(),
): PresenceLabel {
  if (online) return { kind: 'online' }
  if (!lastSeenAt) return { kind: 'never' }
  const then = Date.parse(lastSeenAt)
  if (Number.isNaN(then)) return { kind: 'never' }
  // A server slightly ahead of this clock must not render "in 2 minutes".
  const minutes = Math.max(0, Math.floor((now - then) / 60_000))
  if (minutes < 60) return { kind: 'minutes', value: minutes }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return { kind: 'hours', value: hours }
  return { kind: 'days', value: Math.floor(hours / 24) }
}
