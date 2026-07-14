import { fetchActiveThreats } from './api'
import { useRadar } from './store'
import type { WSMessage } from './types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8137/ws/threats'

let socket: WebSocket | null = null
let retry = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

/** Connect to the backend WS with backoff reconnection and active-set reconcile. */
export function connectWS() {
  if (socket && socket.readyState <= WebSocket.OPEN) return
  clearReconnect() // avoid stacking a pending reconnect with a fresh connect

  socket = new WebSocket(WS_URL)

  socket.onopen = () => {
    retry = 0
    clearReconnect()
    useRadar.getState().setConnected(true)
    // Reconcile: closes/opens missed while disconnected (fixes fetch/WS races).
    fetchActiveThreats().then(useRadar.getState().setThreats).catch(() => {})
  }

  socket.onmessage = (e) => {
    try {
      const msg: WSMessage = JSON.parse(e.data)
      useRadar.getState().handleWS(msg)
    } catch {
      /* ignore malformed frame */
    }
  }

  const scheduleReconnect = () => {
    useRadar.getState().setConnected(false)
    // Headcount is meaningless while we're not connected — clear it so the
    // header doesn't show a stale number until the next 'online' frame.
    useRadar.getState().setOnline(null)
    socket = null
    retry = Math.min(retry + 1, 6)
    clearReconnect()
    reconnectTimer = setTimeout(connectWS, 500 * 2 ** retry)
  }

  socket.onclose = scheduleReconnect
  socket.onerror = () => socket?.close()
}
