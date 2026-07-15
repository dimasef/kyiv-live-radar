import type { FeedEntry, Notice } from '@/types'

const KYIV_TZ = 'Europe/Kyiv'

// YYYY-MM-DD in Kyiv's calendar day, not UTC/browser-local — a message right
// after midnight Kyiv time must group under that new day, not the UTC one.
export function kyivDayKey(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: KYIV_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export function daySeparatorLabel(dayKey: string, lang: string, t: (k: string) => string): string {
  const now = new Date()
  if (dayKey === kyivDayKey(now)) return t('log.today')
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  if (dayKey === kyivDayKey(yesterday)) return t('log.yesterday')
  const label = new Intl.DateTimeFormat(lang === 'uk' ? 'uk-UA' : 'en-US', {
    timeZone: KYIV_TZ,
    day: 'numeric',
    month: 'long',
  }).format(new Date(`${dayKey}T12:00:00Z`))
  return label.charAt(0).toUpperCase() + label.slice(1)
}

// One real message can close several tracks at once (e.g. an untyped
// "Дорозвідка" stand-down) — each gets its own ThreatEvent so it shows up in
// ITS OWN track's inspect view, but that means the SAME raw text would
// otherwise appear as several back-to-back cards in the flat feed, reading
// as a duplicate. Collapse adjacent entries that came from one source
// message into a single card instead.
export function groupFeed(log: FeedEntry[]): FeedEntry[][] {
  const groups: FeedEntry[][] = []
  for (const entry of log) {
    const head = groups[groups.length - 1]?.[0]
    const sameMessage =
      head != null &&
      head.event.source_message_id != null &&
      head.event.source_id === entry.event.source_id &&
      head.event.source_message_id === entry.event.source_message_id &&
      head.event.raw_text === entry.event.raw_text
    if (sameMessage) {
      groups[groups.length - 1].push(entry)
    } else {
      groups.push([entry])
    }
  }
  return groups
}

// One all-clear announced across channels within this window is ONE event —
// collapse the notices into a single card instead of repeating it per source.
const CLEAR_GROUP_MS = 12 * 60 * 1000

/** Cluster the notices timeline: adjacent all-clears within the window become
 * one unit (several sources, one "відбій"); every other notice stays its own. */
export function clusterNotices(notices: Notice[]): Notice[][] {
  const units: Notice[][] = []
  for (const n of notices) {
    const last = units[units.length - 1]
    const joins =
      n.kind === 'clear' &&
      last != null &&
      last[0].kind === 'clear' &&
      Math.abs(new Date(last[0].event_time).getTime() - new Date(n.event_time).getTime()) <=
        CLEAR_GROUP_MS
    if (joins) last.push(n)
    else units.push([n])
  }
  return units
}

export type TimelineItem =
  | { kind: 'group'; time: string; keyId: string; group: FeedEntry[] }
  | { kind: 'notice'; time: string; keyId: string; notices: Notice[] }

/** Merge sighting groups and info notices into one time-sorted timeline;
 * multi-source all-clears are clustered into one unit. */
export function buildTimeline(log: FeedEntry[], notices: Notice[]): TimelineItem[] {
  return [
    ...groupFeed(log).map(
      (group): TimelineItem => ({
        kind: 'group',
        time: group[0].event.event_time,
        keyId: `g${group[0].event.id}`,
        group,
      }),
    ),
    ...clusterNotices(notices).map(
      (units): TimelineItem => ({
        kind: 'notice',
        time: units[0].event_time,
        keyId: `n${units[0].id}`,
        notices: units,
      }),
    ),
  ].sort((a, b) => (a.time < b.time ? 1 : -1))
}
