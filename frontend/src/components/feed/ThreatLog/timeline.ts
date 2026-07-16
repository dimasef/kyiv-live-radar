import type { FeedEntry, Incident, Notice } from '@/types'

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
// The LLM context notices (directional/forecast/status) that several channels
// raise about the SAME thing within a few minutes are one cue, not N.
const CONTEXT_GROUP_MS = 5 * 60 * 1000

/** Whether two adjacent notices are the same event and should share one card:
 * all-clears within 12 min, or same-kind context cues (directional/forecast/
 * status) about the same origin+type within 5 min. Summaries never merge. */
function noticesJoin(a: Notice, b: Notice): boolean {
  if (a.kind !== b.kind) return false
  const dt = Math.abs(new Date(a.event_time).getTime() - new Date(b.event_time).getTime())
  if (a.kind === 'clear') return dt <= CLEAR_GROUP_MS
  if (a.kind === 'directional' || a.kind === 'forecast' || a.kind === 'status') {
    return dt <= CONTEXT_GROUP_MS && a.origin === b.origin && a.target_type === b.target_type
  }
  return false
}

/** Cluster the notices timeline: adjacent same-event notices become one unit
 * (several sources, one cue); every other notice stays its own card. */
export function clusterNotices(notices: Notice[]): Notice[][] {
  const units: Notice[][] = []
  for (const n of notices) {
    const last = units[units.length - 1]
    if (last != null && noticesJoin(last[0], n)) last.push(n)
    else units.push([n])
  }
  return units
}

export type TimelineItem =
  | { kind: 'group'; time: string; keyId: string; group: FeedEntry[] }
  | { kind: 'notice'; time: string; keyId: string; notices: Notice[] }
  | { kind: 'incidentEnd'; time: string; keyId: string; incident: Incident }

/** Merge sighting groups, info notices, and ended-attack summaries into one
 * time-sorted timeline; multi-source cues are clustered into one unit. */
export function buildTimeline(
  log: FeedEntry[],
  notices: Notice[],
  recentIncidents: Incident[] = [],
): TimelineItem[] {
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
    ...recentIncidents
      .filter((inc) => inc.ended_at != null)
      .map(
        (inc): TimelineItem => ({
          kind: 'incidentEnd',
          time: inc.ended_at as string,
          keyId: `i${inc.id}`,
          incident: inc,
        }),
      ),
  ].sort((a, b) => (a.time < b.time ? 1 : -1))
}
