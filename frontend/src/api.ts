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

/** An HTTP error carrying the status code so callers can branch on it (401 vs
 * 403 vs 400) instead of parsing a string. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// --- Auth token plumbing ---------------------------------------------------
// The access token lives in memory only (never localStorage) to shrink the XSS
// exfiltration surface; the refresh token is persisted by the auth store. On a
// 401 we transparently refresh once and retry via `refreshHandler`, which the
// auth store registers (setRefreshHandler) — api.ts stays storage-agnostic.
let accessToken: string | null = null
let refreshHandler: (() => Promise<string | null>) | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}
export function setRefreshHandler(fn: (() => Promise<string | null>) | null): void {
  refreshHandler = fn
}

function withAuth(headers: HeadersInit | undefined, token: string | null): HeadersInit {
  return token ? { ...(headers ?? {}), Authorization: `Bearer ${token}` } : (headers ?? {})
}

/** fetch + bearer token + one transparent refresh-and-retry on 401. */
async function authedFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const res = await fetch(`${API}${path}`, { ...init, headers: withAuth(init.headers, accessToken) })
  if (res.status === 401 && retry && refreshHandler) {
    const fresh = await refreshHandler()
    if (fresh) {
      return fetch(`${API}${path}`, { ...init, headers: withAuth(init.headers, fresh) })
    }
  }
  return res
}

async function get<T>(path: string): Promise<T> {
  const res = await authedFetch(path)
  if (!res.ok) throw new ApiError(res.status, `${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function send<T>(path: string, method: 'POST' | 'DELETE', body: unknown): Promise<T> {
  const res = await authedFetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, `${method} ${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

/** POST that carries NO auth and never triggers the refresh-retry — for the
 * auth endpoints themselves, where a 401 is a real credential error, not an
 * expired access token. */
async function authPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, `POST ${path} -> ${res.status}`)
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

// --- Auth (see store/authSlice.ts + components/auth) -----------------------
export interface AuthUser {
  id: number
  email: string | null
  display_name: string | null
  avatar_url: string | null
  role: string
  /** Linked sign-in methods: 'password' + any of 'google' | 'telegram'. */
  providers: string[]
}
export interface TokenPair {
  access: string
  refresh: string
  token_type: string
  user: AuthUser
}
/** The Telegram Login Widget payload (forwarded verbatim so the backend can
 * re-verify the HMAC over exactly the fields Telegram signed). */
export interface TelegramAuthPayload {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

export const authRegister = (email: string, password: string, displayName?: string) =>
  authPost<TokenPair>('/auth/register', { email, password, display_name: displayName })
export const authLogin = (email: string, password: string) =>
  authPost<TokenPair>('/auth/login', { email, password })
export const authGoogle = (credential: string) =>
  authPost<TokenPair>('/auth/google', { credential })
export const authTelegram = (payload: TelegramAuthPayload) =>
  authPost<TokenPair>('/auth/telegram', payload)
export const authRefreshToken = (refresh: string) =>
  authPost<{ access: string; token_type: string }>('/auth/refresh', { refresh })
export const authMe = () => get<AuthUser>('/auth/me')
export const authLogout = () => authPost<{ ok: boolean }>('/auth/logout', {})
