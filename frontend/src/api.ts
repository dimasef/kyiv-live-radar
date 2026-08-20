import type {
  Alert,
  AlertZone,
  AlertZoneGeometry,
  AnalyticsPeriod,
  District,
  DistrictBoundary,
  FeedEntry,
  HealthStatus,
  Incident,
  Journal,
  JournalStats,
  Notice,
  NoticeKind,
  RawCount,
  RawExportResponse,
  RawLlmStats,
  RawMessagesPage,
  RawOutcomeFilter,
  RawSource,
  Region,
  SourceLink,
  TargetType,
  Threat,
  ThreatAxis,
  ThreatEvent,
} from './types'
import type { components } from './api-types'

type Schemas = components['schemas']

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

async function send<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE' | 'PATCH',
  body?: unknown,
): Promise<T> {
  const res = await authedFetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
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
// The channels this radar reads, for the legend's «Джерела» block. Public and
// deliberately narrow — `fetchSources` below is the ADMIN view of the same
// table and carries trust weights and listener errors with it.
export const fetchPublicSources = () => get<SourceLink[]>('/sources')
export const fetchActiveThreats = () => get<Threat[]>('/threats/active')
export const fetchActiveIncidents = () => get<Incident[]>('/incidents/active')
export const fetchRecentIncidents = (limit = 20) =>
  get<Incident[]>(`/incidents/recent?limit=${limit}`)
export const fetchActiveAxes = () => get<ThreatAxis[]>('/axes/active')
export const fetchActiveAlerts = () => get<Alert[]>('/alerts/active')
export const fetchAlertZones = () => get<AlertZone[]>('/alert-zones')
/** Lazy: only fetched when the raion-alert layer is first switched on. */
export const fetchAlertZoneGeometry = () => get<AlertZoneGeometry>('/alert-zones/geometry')
export const fetchHealth = () => get<HealthStatus>('/health')
export const fetchRecentNotices = (limit = 30) =>
  get<Notice[]>(`/notices/recent?limit=${limit}`)
// `region` narrows the page the feed loads to one watched pool. Without it a
// reader who hides the other regions gets `limit` rows and only a fraction left
// to read — the filter has to reach the query, not just the render.
export const fetchRecentEvents = (limit = 60, region?: Region) =>
  get<FeedEntry[]>(`/events/recent?limit=${limit}${region ? `&region=${region}` : ''}`)
// Per-day threat-activity journal for the calendar page (/journal). `from`/`to`
// are Kyiv-local YYYY-MM-DD; the response spans every day in [from, to].
export const fetchJournal = (from: string, to: string) =>
  get<Journal>(`/journal/days?from=${from}&to=${to}`)
// Across-days aggregation for the journal's statistics tab. Separate route
// because 'all' is uncapped, unlike the 92-day-limited /journal/days.
export const fetchJournalStats = (period: AnalyticsPeriod) =>
  get<JournalStats>(`/journal/stats?period=${period}`)
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

// --- Admin manual controls (see components/admin) — parser overrides. Every
// endpoint is admin-gated server-side; the response mirrors the change, but the
// authoritative update reaches the store via the WS broadcast the server emits.
export const dismissThreat = (id: number) => send<Threat>(`/admin/threats/${id}/dismiss`, 'POST')
export const restoreThreat = (id: number) => send<Threat>(`/admin/threats/${id}/restore`, 'POST')
export const setThreatType = (id: number, target_type: TargetType) =>
  send<Threat>(`/admin/threats/${id}`, 'PATCH', { target_type })
export const dismissIncident = (id: number) =>
  send<Incident>(`/admin/incidents/${id}/dismiss`, 'POST')
export const restoreIncident = (id: number) =>
  send<Incident>(`/admin/incidents/${id}/restore`, 'POST')
export const dismissAlert = (id: number) => send<Alert>(`/admin/alerts/${id}/dismiss`, 'POST')
export const restoreAlert = (id: number) => send<Alert>(`/admin/alerts/${id}/restore`, 'POST')
export const deleteEvent = (id: number) => send<Threat>(`/admin/events/${id}`, 'DELETE')
export const setEventDistrict = (id: number, districtId: number) =>
  send<Threat>(`/admin/events/${id}`, 'PATCH', { district_id: districtId })

/** Publish a raw message to the feed as a notice by hand — for the ones the
 * suppression filters were right to drop in general but wrong to drop here. */
export const addRawNotice = (rawId: number, kind: NoticeKind, text?: string) =>
  send<Notice>(`/admin/raw_messages/${rawId}/notice`, 'POST', { kind, text: text ?? null })
export const deleteNotice = (id: number) => send<void>(`/admin/notices/${id}`, 'DELETE')

export type Dismissed = Schemas['DismissedOut']
export const fetchDismissed = () => get<Dismissed>('/admin/dismissed')

// --- Learning from corrections (admin) — coverage gaps + harvested labels. ---
export type CoverageGap = Schemas['CoverageGapOut']
export const fetchCoverageGaps = (limit = 50, scan?: number) =>
  get<CoverageGap[]>(`/admin/coverage_gaps?limit=${limit}${scan ? `&scan=${scan}` : ''}`)

export type Correction = Schemas['CorrectionOut']
export const fetchCorrections = (limit = 100) =>
  get<Correction[]>(`/admin/corrections?limit=${limit}`)

// --- Sources / channels management (admin) — the DB's active sources ARE the
// live channel list; mutations here make the listener reconnect + re-subscribe.
export type SourceStats = Schemas['SourceStatsOut']
export type Source = Schemas['SourceAdminOut']
export interface SourceCreateBody {
  subscribe_ref: string
  name?: string
  role?: 'spotter' | 'alert'
  region?: Region
  trust_weight?: number
}
export type SourcePatch = Partial<
  Pick<Source, 'name' | 'role' | 'region' | 'trust_weight' | 'is_active'>
>
export type SourceDeleteResult = Schemas['SourceDeleteOut']
export const fetchSources = () => get<Source[]>('/admin/sources')
export const createSource = (body: SourceCreateBody) => send<Source>('/admin/sources', 'POST', body)
export const updateSource = (id: number, patch: SourcePatch) =>
  send<Source>(`/admin/sources/${id}`, 'PATCH', patch)
export const activateSource = (id: number) =>
  send<Source>(`/admin/sources/${id}/activate`, 'POST')
export const deactivateSource = (id: number) =>
  send<Source>(`/admin/sources/${id}/deactivate`, 'POST')
/** HARD delete — removes the channel AND all its stored messages/events. */
export const deleteSource = (id: number) =>
  send<SourceDeleteResult>(`/admin/sources/${id}`, 'DELETE')

// --- Admin reprocess (rebuild tracks from raw messages) — replaces the
// REPROCESS_ON_BOOT env+restart footgun with a guarded, one-click apply. ---
export type ReprocessDay = Schemas['ReprocessDayOut']
export type ReprocessSummary = Schemas['ReprocessSummaryOut']
export type ReprocessPreview = Schemas['ReprocessPreviewOut']
export type ReprocessResult = Schemas['ReprocessResultOut']
/** `last` previews the "rebuild only the tail" scope: the response's
 * `scope_messages`/`scope_from` say what that tail really covers (the server
 * widens it so no track is cut in half). */
export const fetchReprocessPreview = (last?: number) =>
  get<ReprocessPreview>(`/admin/reprocess/preview${last ? `?last=${last}` : ''}`)
export const applyReprocess = (force = false, noLlm = true, last?: number) =>
  send<ReprocessResult>('/admin/reprocess/apply', 'POST', {
    force,
    no_llm: noLlm,
    last: last ?? null,
  })

// --- Web Push (danger near home) — see lib/push.ts for the browser side. ---
export type PushConfig = Schemas['PushConfigOut']
export interface PushSubscribeBody {
  subscription: { endpoint: string; keys: { p256dh: string; auth: string } }
  home: { lat: number; lon: number; radius_km: number } | null
}
export type PushPrefsResult = Schemas['PushPrefsOut']
export const fetchPushConfig = () => get<PushConfig>('/push/config')
/** The prefs from this user's most recent subscription on ANY device — used to
 * seed a new one instead of starting from defaults. */
export const fetchPushPrefs = () => get<PushPrefsResult>('/push/prefs')
export const postPushSubscribe = (body: PushSubscribeBody) =>
  send<{ ok: boolean }>('/push/subscribe', 'POST', body)
export const deletePushSubscribe = (endpoint: string) =>
  send<{ ok: boolean }>('/push/subscribe', 'DELETE', { endpoint })

// --- Auth (see store/authSlice.ts + components/auth) -----------------------
export type AuthUser = Schemas['UserOut']

/** Persist the account-bound gamification toggle (see prefsSlice/authSlice). */
export const setGamificationPref = (enabled: boolean) =>
  send<{ enabled: boolean }>('/me/gamification', 'PUT', { enabled })

/** Roles that carry admin access (service tools / admin routes). Mirrors the
 * backend models.ADMIN_ROLES — 'admin_g' is a manual admin variant. */
export const ADMIN_ROLES = ['admin', 'admin_g']
export const isAdminRole = (role?: string | null): boolean =>
  role != null && ADMIN_ROLES.includes(role)
export type TokenPair = Schemas['TokenPairOut']
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
/** Edit your own profile. Fields left out are untouched; an explicit null
 * clears one (an avatar of null falls back to the monogram). */
export const patchMe = (patch: { display_name?: string | null; avatar_url?: string | null }) =>
  send<AuthUser>('/auth/me', 'PATCH', patch)
export const authLogout = () => authPost<{ ok: boolean }>('/auth/logout', {})

// --- Friends (contacts) + shareable home (see store/friendsSlice.ts) --------
export type HomePoint = Schemas['HomePointOut']
export type FriendUserBrief = Schemas['FriendUserBrief']
export type Friend = Schemas['FriendOut']
export type FriendRequest = Schemas['FriendRequestOut']
export type FriendRequests = Schemas['FriendRequestsOut']
export type MyHome = Schemas['MyHomeOut']
export type FriendAction = Schemas['FriendActionOut']

export const fetchFriends = () => get<Friend[]>('/friends')
export const fetchFriendRequests = () => get<FriendRequests>('/friends/requests')
export const sendFriendRequest = (email: string) =>
  send<FriendAction>('/friends/requests', 'POST', { email })
export const acceptFriendRequest = (id: number) =>
  send<FriendAction>(`/friends/requests/${id}/accept`, 'POST')
export const declineFriendRequest = (id: number) =>
  send<FriendAction>(`/friends/requests/${id}/decline`, 'POST')
export const removeFriend = (userId: number) =>
  send<FriendAction>(`/friends/${userId}`, 'DELETE')
export const fetchMyHome = () => get<MyHome>('/me/home')
/** Store the home on the account. Sharing is a separate call on purpose — every
 * signed-in user's home is saved so it follows them to another device, whether
 * or not they let contacts see it. */
export const putMyHome = (lat: number, lon: number, radius_km: number) =>
  send<MyHome>('/me/home', 'PUT', { lat, lon, radius_km })
export const patchHomeShare = (share: boolean) =>
  send<MyHome>('/me/home/share', 'PATCH', { share })
/** How the owner's own marker is drawn. Both halves go every time — the server
 * writes what it gets, so a null resets that half to the default marker. */
export const patchHomeStyle = (icon: string | null, color: string | null, glow: boolean) =>
  send<MyHome>('/me/home/style', 'PATCH', { icon, color, glow })
export const deleteMyHome = () => send<MyHome>('/me/home', 'DELETE')

/** Another user seen through a contact's contact list — name + picture only;
 * the server withholds the email on purpose (see PublicUserBrief). */
export type PublicUser = Schemas['PublicUserBrief']
/** Who one of your contacts is connected to. 403s for anyone but their own
 * accepted contacts. */
export const fetchUserContacts = (userId: number) =>
  get<PublicUser[]>(`/friends/${userId}/contacts`)

export type ContactPrefs = Schemas['ContactPrefsOut']
export const fetchContactPrefs = () => get<ContactPrefs>('/me/contact_prefs')
export const putContactPref = (
  contactId: number,
  pref: { color?: string; icon?: string; glow?: boolean; hidden?: boolean },
) => send<ContactPrefs>(`/me/contact_prefs/${contactId}`, 'PUT', pref)

export type PresencePref = Schemas['PresencePrefOut']
export const fetchMyPresence = () => get<PresencePref>('/me/presence')
export const putMyPresence = (share_presence: boolean) =>
  send<PresencePref>('/me/presence', 'PUT', { share_presence })

// --- Gamification (collectible card analysis, see store/gameSlice.ts) --------
/** Which of a target's two analyses each covers — 'track' while it flies,
 * 'remains' on its debris after it's shot down. */
export type AnalysisKind = 'track' | 'remains'
export type AnalysisResult = Schemas['AnalyzeOut']
export type ThreatAnalysisState = Schemas['ThreatAnalysisStateOut']
export type CardCount = Schemas['CardCountOut']
export type Collection = Schemas['CollectionOut']
export const postAnalysis = (threatId: number, kind: AnalysisKind) =>
  send<AnalysisResult>('/analysis', 'POST', { threat_id: threatId, kind })
export const fetchThreatAnalysisState = (threatId: number) =>
  get<ThreatAnalysisState>(`/analysis/threat/${threatId}`)
export const fetchCollection = () => get<Collection>('/analysis/collection')
/** A friend's collection (server 403s if not you or an accepted friend). */
export const fetchUserCollection = (userId: number) =>
  get<Collection>(`/collection/${userId}`)

// --- Bug reports (filed by users, worked in the admin console) --------------
export type BugReport = Schemas['BugReportOut']
export type BugReportStatus = BugReport['status']
export type BugContext = Schemas['BugContextIn']
export const submitBugReport = (
  description: string,
  screenshot: string | null,
  context: BugContext,
) => send<Schemas['BugReportAckOut']>('/bug-reports', 'POST', { description, screenshot, context })
export const fetchBugReports = (status?: BugReportStatus) =>
  get<BugReport[]>(`/admin/bug-reports${status ? `?status=${status}` : ''}`)
export const setBugReportStatus = (id: number, status: BugReportStatus) =>
  send<BugReport>(`/admin/bug-reports/${id}`, 'PATCH', { status })
export const deleteBugReport = (id: number) =>
  send<{ deleted: number }>(`/admin/bug-reports/${id}`, 'DELETE')
