import type { District, DistrictBoundary, FeedEntry, Threat } from './types'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8137'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export const fetchDistricts = () => get<District[]>('/districts')
export const fetchBoundaries = () => get<DistrictBoundary[]>('/districts/boundaries')
export const fetchActiveThreats = () => get<Threat[]>('/threats/active')
export const fetchRecentEvents = (limit = 60) =>
  get<FeedEntry[]>(`/events/recent?limit=${limit}`)
