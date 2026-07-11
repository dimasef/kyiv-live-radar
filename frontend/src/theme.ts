import type { Threat } from './types'

export const STATUS_COLORS = {
  confirmed: '#ef4444',
  unconfirmed: '#eab308',
  destroyed: '#6b7280',
  clear: '#22c55e',
  conflict: '#f97316',
  impact: '#d946ef',
} as const

/** Map a threat's status/conflict to a display color. Conflict wins, except an
 * impact (a confirmed strike location) keeps its own distinct color. */
export function threatColor(t: Threat): string {
  if (t.status === 'impact') return STATUS_COLORS.impact
  if (t.has_conflict) return STATUS_COLORS.conflict
  switch (t.status) {
    case 'unconfirmed':
      return STATUS_COLORS.unconfirmed
    case 'destroyed':
    case 'lost':
      return STATUS_COLORS.destroyed
    default:
      return STATUS_COLORS.confirmed
  }
}
