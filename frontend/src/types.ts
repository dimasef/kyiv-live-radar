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
  /** Operator-facing gist from an LLM verdict (inline-llm or a triage rescue) —
   * the feed uses it as the card headline, raw text collapsed beneath. null for
   * rule-only events. */
  llm_summary: string | null
  lat: number | null
  lon: number | null
}

export interface Threat {
  id: number
  created_at: string
  target_type: TargetType
  status: ThreatStatus
  /** 'track' = an inbound target being followed; 'impact' = a closed-on-creation
   * strike marker (a point hit, never a trajectory — see MapView). */
  kind: 'track' | 'impact'
  scope: 'district' | 'city'
  incident_id: number | null
  target_count: number
  closed_at: string | null
  /** Explicit reason a track closed; null while open. See ThreatLog.tsx for
   * how this drives the feed's closed-track label. */
  closed_reason: 'destroyed' | 'all_clear' | 'stand_down' | 'stale' | null
  corroboration_count: number
  has_conflict: boolean
  confidence: number
  events: ThreatEvent[]
}

export interface FeedEntry {
  event: ThreatEvent
  threat: Threat
}

/** Weapon-family classification of an attack, derived server-side (never
 * stored) from its accumulated member types — see backend app/attack.py. */
export type AttackClassification = 'drone' | 'cruise_missile' | 'ballistic' | 'combined' | 'unknown'

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
  /** Distinct raion ids touched by this attack (excludes the citywide sentinel)
   * — the map highlights these polygons for an active incident. */
  district_ids: number[]
  classification: AttackClassification
  attack_types: TargetType[]
  alert_id: number | null
  /** Decoy/EW vocabulary was mentioned — a MODIFIER, not a replacement for
   * `classification` (an attack can be combined AND partly imitation). */
  decoy_suspected: boolean
  has_hypersonic: boolean
  /** Single source of truth for "worth a prominent banner" — computed
   * server-side (see backend serialize.py::_is_notable). */
  notable: boolean
}

/** One тривога→відбій window within a journal day. `seconds` is 0 for an
 * incomplete window (still open / failsafe-closed) so it never wins "longest". */
export interface JournalAlertWindow {
  started_at: string
  ended_at: string | null
  seconds: number
  incomplete: boolean
}

/** One calendar day of aggregated threat activity (GET /journal/days). Mirrors
 * backend schemas.py::JournalDayOut. The intensity score is derived on the
 * client from these fields — see components/journal/journalStats.ts. */
export interface JournalDay {
  /** Kyiv-local ISO date, YYYY-MM-DD. */
  date: string
  attack_count: number
  track_count: number
  target_count: number
  impact_count: number
  type_counts: Record<TargetType, number>
  alert_count: number
  alert_seconds: number
  longest_alert_seconds: number
  /** The day's alert duration is a lower bound (some alert was open/failsafe). */
  alert_incomplete: boolean
  /** Chronological тривога→відбій intervals. */
  alert_windows: JournalAlertWindow[]
  /** Most-active district first (by event count). */
  district_ids: number[]
  district_count: number
}

export interface Journal {
  from_date: string
  to_date: string
  days: JournalDay[]
}

/** A non-threat feed notice. Rule-emitted: 'clear' (відбій) / 'summary' (recap).
 * LLM-triage-emitted context notices: 'directional' (an inbound axis),
 * 'forecast' (an expected strike / threat level), 'status' (PPO/operational).
 * Shown in the event log timeline, never a map threat. */
export type NoticeKind = 'clear' | 'summary' | 'directional' | 'forecast' | 'status'

export interface Notice {
  id: number
  kind: NoticeKind
  text: string
  target_type: TargetType
  event_time: string
  source_id: number | null
  source_name: string | null
  /** Curated origin key for a directional notice (else null). */
  origin: string | null
  /** 'rule' (authoritative) | 'llm' (shown with an "AI · аналіз" badge). */
  generated_by: 'rule' | 'llm'
}

/** A directional threat axis — an inbound bearing/origin ("балістика з
 * Брянщини") with no Kyiv raion. NOT a map point: rendered as a screen-edge
 * wedge along `bearing_deg`. Supplementary, volunteer-sourced. */
export interface ThreatAxis {
  id: number
  sector: string
  /** 0=N, 90=E — the wedge direction from Kyiv toward the origin. */
  bearing_deg: number
  origin_key: string | null
  origin_name: string | null
  /** Representative centroid of the origin region — the axis morphs from an edge
   * wedge into an on-map source marker here when zoomed out. Null for bare-sector
   * axes (a direction with no named place). */
  origin_lat: number | null
  origin_lon: number | null
  target_type: TargetType
  status: 'unverified' | 'corroborated' | 'expired'
  corroboration_count: number
  created_at: string
  last_seen_at: string
  expires_at: string | null
}

/** An official air-raid alert window (тривога -> відбій) from an authoritative
 * source (@KyivCityOfficial today). Independent of Incident — answers "is the
 * siren on" rather than "what's flying". */
export interface Alert {
  id: number
  scope: 'city' | 'oblast'
  alert_type: string
  started_at: string
  ended_at: string | null
  provider: string
  closed_reason: 'official' | 'failsafe' | null
}

export interface WSMessage {
  type:
    | 'event'
    | 'status'
    | 'notice'
    | 'alert'
    | 'attack'
    | 'axis'
    | 'health'
    | 'online'
    | 'hello'
    | 'ping'
  threat?: Threat
  event?: ThreatEvent
  notice?: Notice
  alert?: Alert
  incident?: Incident
  axis?: ThreatAxis
  /** 'health' frame payload — whether the live Telegram feed looks healthy. */
  feed_ok?: boolean | null
  /** 'online' frame payload — how many clients are watching right now. */
  online?: number | null
}

/** GET /health — process status, not pushed over WS (see WSMessage's
 * 'health' frame for the live-updating counterpart of `telegram.feed_ok`). */
export interface HealthStatus {
  status: string
  simulator: boolean
  telegram?: {
    connected: boolean
    last_message_at: string | null
    last_error: string | null
    feed_ok: boolean | null
  }
}

/** One ThreatEvent a raw message produced — the same T{threat_id}/M{event_id}
 * dev badge shown in the feed (see ThreatLog/badges.tsx). A raw message can
 * produce several (an untyped "дорозвідка" can close multiple open tracks
 * at once). */
export interface RawEventLink {
  threat_id: number
  event_id: number
}

/** One verbatim ingested message, INCLUDING ones the parser suppressed or
 * couldn't localize — see GET /raw_messages (the /raw debug route).
 * `outcome`/`events`/`notice_id` are authoritative when `events` is
 * non-empty or `notice_id` is set (a real ThreatEvent/Notice matched);
 * otherwise `outcome` is a best-effort re-derived label. */
export interface RawMessage {
  id: number
  source_id: number | null
  source_name: string | null
  message_id: number | null
  text: string
  event_time: string
  forwarded_from_id: number | null
  reply_to_message_id: number | null
  processed: boolean
  outcome: string
  events: RawEventLink[]
  notice_id: number | null
  /** Whether the LLM fallback was called — null for messages ingested
   * before this was tracked (genuinely unknown, not "no"). */
  llm_attempted: boolean | null
  /** Token usage/cost for that call — set together with llm_attempted when
   * the API call actually completed; null otherwise. */
  llm_input_tokens: number | null
  llm_output_tokens: number | null
  llm_cost_usd: number | null
  /** The full structured triage/extraction the LLM returned — present only
   * when the call produced usable JSON. Collected for /raw audit (Stage 1);
   * nothing in the product routes on it yet. */
  llm_response: LlmResponse | null
  /** Async-triage bookkeeping — where the message went in the triage queue and
   * what routing did with its verdict. null for messages never enqueued. */
  triage_state: string | null
  triage_action: string | null
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

/** Full structured LLM fallback response stored on a raw message — see
 * RawMessage.llm_response and backend parsing/llm.py::llm_extract. */
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

/** One monitored channel, for the /raw channel filter dropdown — see
 * GET /raw_messages/sources. */
export interface RawSource {
  id: number
  name: string
}

/** Aggregate LLM fallback usage across ALL raw messages — see
 * GET /raw_messages/llm_stats. */
export interface RawLlmStats {
  calls: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
}

export interface RawMessagesPage {
  items: RawMessage[]
  /** Pass as `before_id` to fetch the next page; null once there's no more. */
  next_before_id: number | null
}

/** 'event' = became a live sighting; 'suppressed' = everything else. */
export type RawOutcomeFilter = 'event' | 'suppressed'

/** Total matching the current filter — see GET /raw_messages/count. */
export interface RawCount {
  count: number
}

/** All raw messages matching the filter (up to the server cap) — see
 * GET /raw_messages/export. `truncated` = the cap was hit, so it's a partial
 * set. */
export interface RawExportResponse {
  messages: RawMessage[]
  truncated: boolean
}

export interface DistrictBoundary {
  id: number
  name_uk: string
  name_en: string
  geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon
}
