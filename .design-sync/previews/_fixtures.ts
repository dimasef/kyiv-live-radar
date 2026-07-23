// Shared typed fixtures for the authored preview cards. Realistic Kyiv-radar
// domain data — never foo/test — since these cards are browsed by humans and
// imitated by the design agent. Imported relatively by each <Name>.tsx.
import type {
  Alert,
  Incident,
  JournalDay,
  Notice,
  TargetType,
  Threat,
  ThreatEvent,
} from '@/types'

const event = (o: Partial<ThreatEvent> = {}): ThreatEvent => ({
  id: 7,
  threat_id: 42,
  district_id: 5,
  raw_text: 'Шахед над Троєщиною, курс південно-західний',
  event_time: '2026-07-22T21:14:00Z',
  confidence: 0.9,
  decision_source: 'rule',
  translated_text: null,
  source_id: 1,
  source_name: 'Київ ППО',
  source_message_id: 1,
  forwarded_from_id: null,
  event_target_type: 'shahed',
  event_target_count: 1,
  llm_summary: null,
  lat: null,
  lon: null,
  ...o,
})

export const threat = (o: Partial<Threat> = {}): Threat => ({
  id: 42,
  created_at: '2026-07-22T21:10:00Z',
  target_type: 'shahed',
  status: 'tracking',
  kind: 'track',
  scope: 'district',
  incident_id: 13,
  target_count: 2,
  closed_at: null,
  closed_reason: null,
  corroboration_count: 3,
  has_conflict: false,
  confidence: 0.86,
  events: [event()],
  ...o,
})

export const notice = (o: Partial<Notice> = {}): Notice => ({
  id: 88,
  kind: 'clear',
  text: 'Відбій повітряної тривоги у Києві. Дякуємо силам ППО за роботу.',
  target_type: 'shahed',
  event_time: '2026-07-22T22:03:00Z',
  source_id: 1,
  source_name: 'Київ ППО',
  origin: null,
  generated_by: 'rule',
  ...o,
})

export const incident = (o: Partial<Incident> = {}): Incident => ({
  id: 13,
  started_at: '2026-07-22T20:40:00Z',
  ended_at: '2026-07-22T22:05:00Z',
  target_type: 'shahed',
  status: 'ended',
  track_count: 9,
  impact_count: 2,
  citywide: true,
  district_count: 5,
  district_ids: [1, 3, 5, 7, 9],
  classification: 'combined',
  attack_types: ['shahed', 'ballistic'],
  alert_id: 4,
  decoy_suspected: true,
  has_hypersonic: true,
  notable: true,
  ...o,
})

export const alert = (o: Partial<Alert> = {}): Alert => ({
  id: 4,
  scope: 'city',
  alert_type: 'air',
  started_at: '2026-07-22T20:41:00Z',
  ended_at: null,
  provider: 'KyivCityOfficial',
  closed_reason: null,
  ...o,
})

const zeroTypes = (): Record<TargetType, number> => ({
  shahed: 0,
  jet_drone: 0,
  missile: 0,
  ballistic: 0,
  unknown: 0,
})

const journalDay = (date: string, o: Partial<JournalDay> = {}): JournalDay => ({
  date,
  attack_count: 1,
  track_count: 3,
  target_count: 5,
  impact_count: 0,
  type_counts: { ...zeroTypes(), shahed: 5 },
  alert_count: 1,
  alert_seconds: 3600,
  longest_alert_seconds: 3600,
  alert_incomplete: false,
  alert_windows: [],
  district_ids: [1, 3],
  district_count: 2,
  ...o,
})

/** A July of activity with a spread of intensities and two ballistic days
 * (violet dot), for the month heatmap. */
export const heatmapDays = (): Map<string, JournalDay> => {
  const m = new Map<string, JournalDay>()
  const mk = (day: number, targets: number, impacts = 0, ballistic = 0) => {
    const date = `2026-07-${String(day).padStart(2, '0')}`
    m.set(
      date,
      journalDay(date, {
        target_count: targets,
        impact_count: impacts,
        attack_count: ballistic > 0 ? 2 : 1,
        type_counts: { ...zeroTypes(), shahed: Math.max(0, targets - ballistic), ballistic },
      }),
    )
  }
  mk(3, 2)
  mk(7, 8)
  mk(9, 3)
  mk(12, 24, 1, 4)
  mk(15, 12)
  mk(18, 40, 3, 6)
  mk(20, 6)
  mk(22, 18, 1, 2)
  return m
}
