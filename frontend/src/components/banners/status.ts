import { useEffect, useState } from 'react'

import { effectiveRegion } from '@/lib/regions'
import type { Alert, Incident, Region, RegionInfo, TargetType } from '@/types'

export const CLEAR_LINGER_MS = 20000

const DRONE_FAMILY = new Set<TargetType>(['shahed', 'jet_drone', 'fpv'])
const SEVERITY: Record<string, number> = { ballistic: 3, missile: 2, drone: 1 }

const severity = (type: TargetType) => SEVERITY[DRONE_FAMILY.has(type) ? 'drone' : type] ?? 0

/** Narrow attacks to the region this reader is actually following.
 *
 * Alerts have since moved one granularity finer — see coverage.ts, which asks
 * about the reader's RAION, because region `kyiv` covers both the city and the
 * oblast around it. An incident is still a region-level thing.
 *
 * Both carry their own region now (backend migration 0036), so the banner asks
 * the direct question. It used to ask an indirect one — "is the reader showing
 * the home region at all?" — because neither had a region and the server only
 * ever opened them for Kyiv, which showed a Сумщина reader Kyiv's air-raid
 * siren as their own situation, in the loudest element on the screen.
 *
 * Asked of the FOLLOWED region, not of the feed's region set: a Сумщина reader
 * who adds Київщина as a secondary feed region wants Kyiv sightings in their
 * timeline, not a Kyiv siren banner over their own oblast.
 *
 * Nothing is narrowed only when there is no followed region to narrow to —
 * the reader has chosen none AND the catalogue has not arrived to supply a
 * home one (the first paint, before the boot fetch lands). Failing towards
 * showing an alert is the only safe direction there. An explicit choice is
 * enough on its own, catalogue or not: someone who has said they are in
 * Сумщина is not shown Kyiv's siren while the boot fetch is in flight.
 */
export function inFollowedRegion<T extends { region: Region }>(
  items: T[],
  catalogue: RegionInfo[],
  chosen: Region | null,
): T[] {
  const followed = effectiveRegion(catalogue, chosen)
  return followed === null ? items : items.filter((i) => i.region === followed)
}


export function notableIncident(incidents: Incident[]): Incident | null {
  const notable = incidents.filter((i) => i.notable)
  if (notable.length === 0) return null
  return [...notable].sort((a, b) => severity(b.target_type) - severity(a.target_type))[0]
}

export function mostRecentlyEnded(alerts: Alert[]): Alert | null {
  return alerts.find((a) => a.ended_at) ?? null
}

/** Which episode the banner was collapsed on. Collapsing is remembered across
 * reloads (an alert outlives the page), but it must NOT carry into the next
 * one: someone who shrank the pill during a quiet night has to see the banner
 * open when a new alert — or a new attack inside the same alert — starts. */
export interface CollapsedFor {
  alert: number | null
  incident: number | null
}

export function stillCollapsed(
  saved: CollapsedFor | null,
  alertId: number | null,
  incidentId: number | null,
): boolean {
  if (saved == null || saved.alert !== alertId) return false
  // An attack ENDING is not a new episode — keep the pill as the user left it.
  return incidentId === null || saved.incident === incidentId
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function useNow(active: boolean): number {
  const [, tick] = useState(0)
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [active])
  return Date.now()
}
