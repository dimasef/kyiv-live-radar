import { useEffect, useState } from 'react'

import { effectiveRegion, homeRegion } from '@/lib/regions'
import type { Alert, Incident, Region, RegionInfo, TargetType } from '@/types'

export const CLEAR_LINGER_MS = 20000

const DRONE_FAMILY = new Set<TargetType>(['shahed', 'jet_drone', 'fpv'])
const SEVERITY: Record<string, number> = { ballistic: 3, missile: 2, drone: 1 }

const severity = (type: TargetType) => SEVERITY[DRONE_FAMILY.has(type) ? 'drone' : type] ?? 0

/** Whether this reader's banner may speak about an alert or an attack at all.
 *
 * Both an `Alert` and an `Incident` are about the HOME region by construction —
 * neither carries a region of its own, and the server only ever opens them for
 * it (backend regions.py: "Only 'kyiv' feeds incidents, the city alert, the
 * journal and home-danger push"). Without this a reader following Сумщина was
 * shown Kyiv's air-raid siren as their own situation, in the loudest element on
 * the screen.
 *
 * Asked of the FOLLOWED region, not of the feed's region set: a Сумщина reader
 * who adds Київщина as a secondary feed region wants Kyiv sightings in their
 * timeline, not a Kyiv siren banner over their own oblast. Home comes from the
 * server catalogue rather than a hardcoded id, so an empty catalogue (the first
 * paint, before the boot fetch lands) shows the banner rather than hiding it —
 * failing towards showing an alert is the only safe direction here.
 */
export function watchesHomeRegion(
  catalogue: RegionInfo[],
  chosen: Region | null,
): boolean {
  const home = homeRegion(catalogue)
  return home === null || effectiveRegion(catalogue, chosen) === home
}


export function notableIncident(incidents: Incident[]): Incident | null {
  const notable = incidents.filter((i) => i.notable)
  if (notable.length === 0) return null
  return [...notable].sort((a, b) => severity(b.target_type) - severity(a.target_type))[0]
}

export function primaryAlert(alerts: Alert[]): Alert | null {
  const open = alerts.filter((a) => !a.ended_at)
  return open.find((a) => a.scope === 'city') ?? open[0] ?? null
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
