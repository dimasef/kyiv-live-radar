export interface District {
  id: number
  name_uk: string
  name_en: string
  lat: number
  lon: number
  aliases: string[]
}

export type TargetType = 'shahed' | 'jet_drone' | 'missile' | 'ballistic' | 'unknown'
export type ThreatStatus = 'unconfirmed' | 'tracking' | 'destroyed' | 'lost' | 'impact'

export interface ThreatEvent {
  id: number
  threat_id: number
  district_id: number
  raw_text: string
  event_time: string
  confidence: number
  decision_source: string
  translated_text: string | null
  source_id: number | null
  source_name: string | null
  source_message_id: number | null
  forwarded_from_id: number | null
  event_target_type: string | null
  /** Group size known as of this event; the feed shows this, not the track's
   * final count. null for pre-column events (fall back to threat.target_count). */
  event_target_count: number | null
  lat: number | null
  lon: number | null
}

export interface Threat {
  id: number
  created_at: string
  target_type: TargetType
  status: ThreatStatus
  scope: 'district' | 'city'
  incident_id: number | null
  target_count: number
  closed_at: string | null
  corroboration_count: number
  has_conflict: boolean
  confidence: number
  events: ThreatEvent[]
}

export interface FeedEntry {
  event: ThreatEvent
  threat: Threat
}

/** A coordinated attack — the umbrella over one alert's tracks/impacts/city
 * alerts, with counts aggregated server-side. */
export interface Incident {
  id: number
  started_at: string
  ended_at: string | null
  target_type: TargetType
  status: 'active' | 'ended'
  track_count: number
  impact_count: number
  citywide: boolean
  district_count: number
}

/** A non-threat feed notice — an all-clear or a retrospective attack summary.
 * Shown in the event log timeline, but never a map threat. */
export interface Notice {
  id: number
  kind: 'clear' | 'summary'
  text: string
  target_type: TargetType
  event_time: string
  source_id: number | null
  source_name: string | null
}

export interface WSMessage {
  type: 'event' | 'status' | 'notice' | 'hello'
  threat?: Threat
  event?: ThreatEvent
  notice?: Notice
}

export interface DistrictBoundary {
  id: number
  name_uk: string
  name_en: string
  geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon
}
