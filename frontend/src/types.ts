/** Server response shapes are aliased from the generated `api-types.ts`, never
 * re-declared. Add a hand-written interface here only when OpenAPI cannot
 * describe it (see the bottom of the file); otherwise give the route a
 * `response_model` on the backend and regenerate. */

import type { components } from './api-types'

type Schemas = components['schemas']

export type District = Schemas['DistrictOut']
export type SourceLink = Schemas['SourceLinkOut']
export type ThreatEvent = Schemas['ThreatEventOut']
export type Threat = Schemas['ThreatOut']
export type FeedEntry = Schemas['FeedEntryOut']
export type Incident = Schemas['IncidentOut']
export type JournalAlertWindow = Schemas['JournalAlertWindowOut']
export type JournalDay = Schemas['JournalDayOut']
export type Journal = Schemas['JournalOut']
export type JournalStats = Schemas['JournalStatsOut']
export type StatsDay = Schemas['StatsDayOut']
export type StatsTotals = Schemas['StatsTotalsOut']
export type HourBucket = Schemas['HourBucketOut']
export type DurationBucket = Schemas['DurationBucketOut']
export type DistrictStat = Schemas['DistrictStatOut']
export type AnalyticsPeriod = JournalStats['period']
export type Notice = Schemas['NoticeOut']
export type ThreatAxis = Schemas['AxisOut']
export type Alert = Schemas['AlertOut']
export type RawEventLink = Schemas['RawEventLinkOut']
/** `llm_response` is an untyped JSON column server-side, so OpenAPI can only
 * call it "an object". The real shape is `LlmResponse` below — overriding just
 * that one field keeps the rest of the row generated. */
export type RawMessage = Omit<Schemas['RawMessageOut'], 'llm_response'> & {
  llm_response: LlmResponse | null
}
export type RawSource = Schemas['RawSourceOut']
export type RawLlmStats = Schemas['RawLlmStatsOut']
export type RawCount = Schemas['RawCountOut']
// Both carry rows, so both take the `llm_response`-corrected RawMessage above.
export type RawMessagesPage = Omit<Schemas['RawMessagesPage'], 'items'> & {
  items: RawMessage[]
}
export type RawExportResponse = Omit<Schemas['RawExportOut'], 'messages'> & {
  messages: RawMessage[]
}
export type User = Schemas['UserOut']
export type TokenPair = Schemas['TokenPairOut']
export type Friend = Schemas['FriendOut']
export type FriendUserBrief = Schemas['FriendUserBrief']
export type FriendRequests = Schemas['FriendRequestsOut']
export type HomePoint = Schemas['HomePointOut']
export type MyHome = Schemas['MyHomeOut']
export type Collection = Schemas['CollectionOut']
export type CardCount = Schemas['CardCountOut']
export type AnalysisResult = Schemas['AnalyzeOut']
export type ThreatAnalysisState = Schemas['ThreatAnalysisStateOut']

export type TargetType = Threat['target_type']
export type ThreatStatus = Threat['status']
export type ThreatKind = Threat['kind']
/** Watched region — 'kyiv' (м. Київ + Київська обл., what the journal, the
 * attack banner and home-danger push are about) or 'chernihiv' (the northern
 * early-warning approach). */
export type Region = Threat['region']
export type ClosedReason = NonNullable<Threat['closed_reason']>
/** Weapon-family classification of an attack, derived server-side (never
 * stored) from its accumulated member types — see backend domain/attack.py. */
export type AttackClassification = Incident['classification']
export type NoticeKind = Notice['kind']
export type AlertScope = Alert['scope']
export type AxisStatus = ThreatAxis['status']
export type AlertZone = Schemas['AlertZoneOut']

/** GET /alert-zones/geometry — `response_model`-less for the same reason as
 * /districts/boundaries: the GeoJSON geometry is passed through verbatim, and
 * OpenAPI can only call it "an object". Keyed by zone_id. */
export type AlertZoneGeometry = Record<
  string,
  { name_uk: string; oblast: string; geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon }
>

/** Sent on every frame — the server's clock. The map's staleness fade runs
 * against absolute `stale_at` timestamps, so a device whose own clock is off
 * needs this to age targets correctly (see store/clockSlice). */
interface WSCommon {
  server_time?: string | null
}

/** Envelope pushed over `/ws/threats`. Not part of OpenAPI — FastAPI only
 * documents HTTP routes — so this one mirror stays manual.
 *
 * A real discriminated union, not a flat interface with every payload
 * optional: `handleWS` switches on `type` with an exhaustive default, so a
 * frame added on the backend and forgotten here fails the BUILD instead of
 * being silently dropped at runtime. Each member carries exactly the payload
 * its producer sends — see broadcast.py, keepalive.py and feeds/alert_zones.py. */
export type WSMessage = WSCommon &
  (
    // The two track-bearing frames: a new sighting, or a track whose state
    // changed with no event of its own (a close, a retype).
    | { type: 'event'; threat: Threat; event?: ThreatEvent | null }
    | { type: 'status'; threat: Threat; event?: ThreatEvent | null }
    | { type: 'notice'; notice: Notice }
    | { type: 'alert'; alert: Alert }
    | { type: 'attack'; incident: Incident }
    | { type: 'axis'; axis: ThreatAxis }
    /** The raions whose siren state just changed. */
    | { type: 'zones'; zones: AlertZone[] }
    /** Whether the live Telegram feed looks healthy. */
    | { type: 'health'; feed_ok: boolean | null }
    /** How many clients are watching right now. */
    | { type: 'online'; online: number | null }
    /** Keepalive — carries nothing but `server_time`. */
    | { type: 'ping' }
  )

/** GET /health — declares no `response_model` (it assembles a plain dict), so
 * it is absent from the generated types. */
export interface HealthStatus {
  status: string
  simulator: boolean
  /** Server clock, hydrating the fade's time reference before the first WS ping. */
  server_time?: string | null
  telegram?: {
    connected: boolean
    last_message_at: string | null
    last_error: string | null
    feed_ok: boolean | null
  }
}

/** GET /districts/boundaries — also `response_model`-less, because the GeoJSON
 * geometry is passed through verbatim from the DB. */
export interface DistrictBoundary {
  id: number
  name_uk: string
  name_en: string
  geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

/** LLM triage category — WHICH kind of message a district-less call saw.
 * Reported by the model, not acted on yet (Stage 1 collect-only). */
export type LlmCategory =
  | 'localized'
  | 'citywide'
  | 'directional'
  | 'forecast'
  | 'status'
  | 'noise'

/** The structured LLM response stored on a raw message. Server-side this is an
 * untyped JSON column, so OpenAPI only knows it as an object — the shape lives
 * here and in backend parsing/llm.py::llm_extract. */
export interface LlmResponse {
  category: LlmCategory
  /** Worth showing an operator even without a localized district. */
  surface: boolean
  /** Short Ukrainian operator-facing line when surface is true; '' otherwise. */
  summary: string
  district_ids: number[]
  target_type: string
  status: string
  is_new_target: boolean
  confidence: number
  /** Curated origin toponym / compass sector for a directional message (Stage 2
   * schema). 'none' when the model named neither. */
  origin_place?: string
  origin_sector?: string
}

/** Client-side only: the /raw outcome filter's two states. 'event' = became a
 * live sighting; 'suppressed' = everything else. */
export type RawOutcomeFilter = 'event' | 'suppressed'
