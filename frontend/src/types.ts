export interface District {
  id: number
  name_uk: string
  name_en: string
  lat: number
  lon: number
  aliases: string[]
}

export type TargetType = 'shahed' | 'jet_drone' | 'missile' | 'unknown'
export type ThreatStatus = 'unconfirmed' | 'tracking' | 'destroyed' | 'lost'

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
  forwarded_from_id: number | null
  event_target_type: string | null
  lat: number | null
  lon: number | null
}

export interface Threat {
  id: number
  created_at: string
  target_type: TargetType
  status: ThreatStatus
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

export interface WSMessage {
  type: 'event' | 'status' | 'hello'
  threat?: Threat
  event?: ThreatEvent
}

export interface DistrictBoundary {
  id: number
  name_uk: string
  name_en: string
  geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon
}
