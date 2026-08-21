import type { StateCreator } from 'zustand'

import { assertNever } from '@/lib/assertNever'
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
    // Every keepalive carries the server's clock — the reference the map's
    // staleness fade is measured against (see clockSlice.clockSkewMs).
    if (msg.server_time) get().setServerTime(msg.server_time)

    // Exhaustive by construction: WSMessage is a discriminated union and the
    // default arm is a `never` check, so a frame the backend starts sending
    // and this switch doesn't handle breaks the build. It used to be an
    // if-chain ending in an untyped `if (msg.threat)` fallback, which is how
    // 'status' came to be handled only by accident.
    switch (msg.type) {
      case 'ping':
        return
      case 'health':
        get().setFeedOk(msg.feed_ok ?? null)
        return
      case 'online':
        get().setOnline(msg.online ?? null)
        return
      case 'alert':
        get().upsertAlert(msg.alert)
        return
      case 'attack':
        get().upsertIncident(msg.incident)
        return
      case 'notice':
        get().upsertNotice(msg.notice)
        return
      case 'axis':
        get().upsertAxis(msg.axis)
        return
      case 'zones':
        get().setZones(msg.zones)
        return
      case 'event':
      case 'status':
        get().applyThreatMessage({
          type: msg.type,
          threat: msg.threat,
          event: msg.event ?? undefined,
        })
        return
      default:
        assertNever(msg)
    }
  },
})
