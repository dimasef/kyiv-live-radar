import type { StateCreator } from 'zustand'

import type { WSMessage } from '@/types'

import type { RadarState } from './types'

export interface WsSlice {
  handleWS: (msg: WSMessage) => void
}

// Pure protocol-level dispatch — each branch hands the message straight to
// the domain slice that owns how to merge it; the merge logic itself lives
// there, not here.
export const createWsSlice: StateCreator<RadarState, [], [], WsSlice> = (_set, get) => ({
  handleWS: (msg) => {
    if (msg.type === 'health') {
      get().setFeedOk(msg.feed_ok ?? null)
      return
    }
    if (msg.type === 'online') {
      get().setOnline(msg.online ?? null)
      return
    }
    if (msg.type === 'alert' && msg.alert) {
      get().upsertAlert(msg.alert)
      return
    }
    if (msg.type === 'attack' && msg.incident) {
      get().upsertIncident(msg.incident)
      return
    }
    if (msg.type === 'notice' && msg.notice) {
      get().upsertNotice(msg.notice)
      return
    }
    if (msg.threat) {
      get().applyThreatMessage({ type: msg.type, threat: msg.threat, event: msg.event })
    }
  },
})
