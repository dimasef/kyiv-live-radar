import type {
  Alert,
  District,
  DistrictBoundary,
  FeedEntry,
  HealthStatus,
  Incident,
  Journal,
  Notice,
  RawCount,
  RawExportResponse,
  RawLlmStats,
  RawMessagesPage,
  RawOutcomeFilter,
  RawSource,
  Threat,
  ThreatAxis,
  ThreatEvent,
} from './types'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8137'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function send<T>(path: string, method: 'POST' | 'DELETE', body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export const fetchDistricts = () => get<District[]>('/districts')
export const fetchBoundaries = () => get<DistrictBoundary[]>('/districts/boundaries')
export const fetchActiveThreats = () => get<Threat[]>('/threats/active')
export const fetchActiveIncidents = () => get<Incident[]>('/incidents/active')
export const fetchRecentIncidents = (limit = 20) =>
  get<Incident[]>(`/incidents/recent?limit=${limit}`)
export const fetchActiveAxes = () => get<ThreatAxis[]>('/axes/active')
export const fetchActiveAlerts = () => get<Alert[]>('/alerts/active')
export const fetchHealth = () => get<HealthStatus>('/health')
export const fetchRecentNotices = (limit = 30) =>
  get<Notice[]>(`/notices/recent?limit=${limit}`)
export const fetchRecentEvents = (limit = 60) =>
  get<FeedEntry[]>(`/events/recent?limit=${limit}`)
// Per-day threat-activity journal for the calendar page (/journal). `from`/`to`
// are Kyiv-local YYYY-MM-DD; the response spans every day in [from, to].
export const fetchJournal = (from: string, to: string) =>
  get<Journal>(`/journal/days?from=${from}&to=${to}`)
// Full event history for one track (oldest -> newest), including closed/
// destroyed ones — used to draw a track on the map for a feed item click,
// independent of the live `threats` map (which evicts closed tracks after
// a few seconds).
export const fetchThreatEvents = (threatId: number) =>
  get<ThreatEvent[]>(`/threats/${threatId}/events`)
// Debug view (see /raw route): every ingested message, cursor-paginated
// newest-first — pass the previous page's next_before_id to page further back.
// The filter fields are shared with count/export so all three agree.
export interface RawMessagesFilter {
  q?: string
  outcome?: RawOutcomeFilter
  llm?: 'yes' | 'no'
  sourceId?: number
}
export interface RawMessagesQuery extends RawMessagesFilter {
  beforeId?: number
  limit?: number
}

function rawFilterParams(f: RawMessagesFilter): URLSearchParams {
  const params = new URLSearchParams()
  if (f.q) params.set('q', f.q)
  if (f.outcome) params.set('outcome', f.outcome)
  if (f.llm) params.set('llm', f.llm)
  if (f.sourceId != null) params.set('source_id', String(f.sourceId))
  return params
}

export const fetchRawMessages = ({ beforeId, limit = 50, ...filter }: RawMessagesQuery = {}) => {
  const params = rawFilterParams(filter)
  params.set('limit', String(limit))
  if (beforeId != null) params.set('before_id', String(beforeId))
  return get<RawMessagesPage>(`/raw_messages?${params}`)
}
// Total matching the filter, for the "показано N з M" counter.
export const fetchRawCount = (filter: RawMessagesFilter = {}) =>
  get<RawCount>(`/raw_messages/count?${rawFilterParams(filter)}`)
// All messages matching the filter (up to the server cap), for offline export.
export const fetchRawExport = (filter: RawMessagesFilter = {}) =>
  get<RawExportResponse>(`/raw_messages/export?${rawFilterParams(filter)}`)
// Aggregate LLM fallback usage across all raw messages (unfiltered) — the
// analytics strip on /raw.
export const fetchRawLlmStats = () => get<RawLlmStats>('/raw_messages/llm_stats')
// Every monitored channel, for the /raw channel filter dropdown.
export const fetchRawSources = () => get<RawSource[]>('/raw_messages/sources')

// --- Web Push (danger near home) — see lib/push.ts for the browser side. ---
export interface PushConfig {
  enabled: boolean
  /** VAPID public key for pushManager.subscribe; fetched at runtime so a key
   * rotation never needs a frontend rebuild. */
  public_key: string | null
}
export interface PushSubscribeBody {
  subscription: { endpoint: string; keys: { p256dh: string; auth: string } }
  home: { lat: number; lon: number; radius_km: number } | null
}
export const fetchPushConfig = () => get<PushConfig>('/push/config')
export const postPushSubscribe = (body: PushSubscribeBody) =>
  send<{ ok: boolean }>('/push/subscribe', 'POST', body)
export const deletePushSubscribe = (endpoint: string) =>
  send<{ ok: boolean }>('/push/subscribe', 'DELETE', { endpoint })
