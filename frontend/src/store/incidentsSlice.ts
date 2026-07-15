import type { StateCreator } from 'zustand'

import type { Incident } from '@/types'

import type { RadarState } from './types'

export interface IncidentsSlice {
  incidents: Incident[]
  setIncidents: (i: Incident[]) => void
  /** Attack (incident) state pushed straight from the server on every change.
   * Ended incidents drop out of the (implicitly "active") list; otherwise
   * replaces by id. */
  upsertIncident: (incident: Incident) => void
}

export const createIncidentsSlice: StateCreator<RadarState, [], [], IncidentsSlice> = (set) => ({
  incidents: [],
  setIncidents: (i) => set({ incidents: i }),
  upsertIncident: (incident) =>
    set((s) => ({
      incidents:
        incident.status === 'ended'
          ? s.incidents.filter((i) => i.id !== incident.id)
          : [incident, ...s.incidents.filter((i) => i.id !== incident.id)],
    })),
})
