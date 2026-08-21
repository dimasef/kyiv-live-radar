import { useEffect, useState } from 'react'

import type { Alert, Incident, TargetType } from '@/types'

export const CLEAR_LINGER_MS = 20000

const DRONE_FAMILY = new Set<TargetType>(['shahed', 'jet_drone'])
const SEVERITY: Record<string, number> = { ballistic: 3, missile: 2, drone: 1 }

const severity = (type: TargetType) => SEVERITY[DRONE_FAMILY.has(type) ? 'drone' : type] ?? 0

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
