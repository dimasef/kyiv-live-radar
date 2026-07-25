import type { StateCreator } from 'zustand'

import type { Incident } from '@/types'

import type { RadarState } from './types'

const RECENT_CAP = 20

export interface IncidentsSlice {
  incidents: Incident[]
  /** Recently ENDED attacks, newest first — the feed renders an attack-summary
   * card at each one's ended_at. An incident moves here (out of `incidents`)
   * when its ending frame arrives, so the summary renders without a refetch. */
  recentIncidents: Incident[]
  /** Feed->map link: the incident whose member districts/tracks the map should
   * highlight, set when the operator taps an "Атака #N" chip. null = none. */
  focusedIncidentId: number | null
  setIncidents: (i: Incident[]) => void
  setRecentIncidents: (i: Incident[]) => void
  focusIncident: (id: number | null) => void
  /** Attack (incident) state pushed straight from the server on every change.
   * An ended incident drops out of the (implicitly "active") list and is
   * recorded in recentIncidents; otherwise replaces by id. */
  upsertIncident: (incident: Incident) => void
}

export const createIncidentsSlice: StateCreator<RadarState, [], [], IncidentsSlice> = (set) => ({
  incidents: [],
  recentIncidents: [],
  focusedIncidentId: null,
  setIncidents: (i) => set({ incidents: i }),
  setRecentIncidents: (i) => set({ recentIncidents: i }),
  focusIncident: (id) => set({ focusedIncidentId: id }),
  upsertIncident: (incident) =>
    set((s) => {
      const activeRest = s.incidents.filter((i) => i.id !== incident.id)
      const recentRest = s.recentIncidents.filter((i) => i.id !== incident.id)
      // An admin-cancelled false positive is not a real attack — drop it from
      // both the active list AND the recent-attack summary cards.
      if (incident.ended_reason === 'dismissed') {
        return { incidents: activeRest, recentIncidents: recentRest }
      }
      return incident.status === 'ended'
        ? {
            incidents: activeRest,
            recentIncidents: [incident, ...recentRest].slice(0, RECENT_CAP),
          }
        : { incidents: [incident, ...activeRest], recentIncidents: s.recentIncidents }
    }),
})
