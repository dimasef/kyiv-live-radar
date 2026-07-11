import type {
  District,
  DistrictBoundary,
  FeedEntry,
  Incident,
  Notice,
  Threat,
  ThreatEvent,
} from './types'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8137'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export const fetchDistricts = () => get<District[]>('/districts')
export const fetchBoundaries = () => get<DistrictBoundary[]>('/districts/boundaries')
export const fetchActiveThreats = () => get<Threat[]>('/threats/active')
export const fetchActiveIncidents = () => get<Incident[]>('/incidents/active')
export const fetchRecentNotices = (limit = 30) =>
  get<Notice[]>(`/notices/recent?limit=${limit}`)
export const fetchRecentEvents = (limit = 60) =>
  get<FeedEntry[]>(`/events/recent?limit=${limit}`)
// Full event history for one track (oldest -> newest), including closed/
// destroyed ones — used to draw a track on the map for a feed item click,
// independent of the live `threats` map (which evicts closed tracks after
// a few seconds).
export const fetchThreatEvents = (threatId: number) =>
  get<ThreatEvent[]>(`/threats/${threatId}/events`)
