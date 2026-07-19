import { useRadar } from './store'
import { hydrate, lastHydrateAt } from './store/bootstrap'
import type { WSMessage } from './types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8137/ws/threats'

// The backend pushes a 'ping' keepalive frame every ~25s (ws_keepalive_s) —
// a healthy socket never goes this long without SOME frame. If it does, the
// socket is a "zombie": readyState still reports OPEN but the peer is gone
// and no `close` event ever fired (this is common after a mobile tab is
// frozen in the background overnight).
const STALE_MS = 60_000
const WATCHDOG_INTERVAL_MS = 20_000
// Coalesces near-simultaneous triggers (e.g. a background-resume event and
// the watchdog firing together) into a single reconnect+rehydrate.
const RESYNC_DEBOUNCE_MS = 3_000
// A hydrate younger than this + a live socket = resume is a no-op.
const RESYNC_MIN_FRESH_MS = 10_000

let socket: WebSocket | null = null
let retry = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let lastMessageAt = Date.now()
let resyncTimer: ReturnType<typeof setTimeout> | null = null
let resyncInFlight = false
let watchdogStarted = false

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

/** Connect to the backend WS with backoff reconnection and full-state reconcile. */
export function connectWS() {
  if (socket && socket.readyState <= WebSocket.OPEN) return
  clearReconnect() // avoid stacking a pending reconnect with a fresh connect

  socket = new WebSocket(WS_URL)

  socket.onopen = () => {
    retry = 0
    lastMessageAt = Date.now()
    clearReconnect()
    useRadar.getState().setConnected(true)
    // Reconcile every active/recent slice: closes/ends/clears missed while
    // disconnected would otherwise linger until a manual reload.
    hydrate()
  }

  socket.onmessage = (e) => {
    lastMessageAt = Date.now()
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

  startWatchdog()
}

/** Tears down the current socket WITHOUT the normal backoff path (detaches
 * `onclose`/`onerror` first so the old socket's eventual, delayed close can't
 * race a fresh connect), then reconnects immediately. This is how we get past
 * a zombie socket: the `readyState <= OPEN` guard in `connectWS` would
 * otherwise refuse to open a new one. */
function forceReconnect() {
  clearReconnect()
  if (socket) {
    socket.onclose = null
    socket.onerror = null
    socket.close()
    socket = null
  }
  retry = 0
  connectWS()
}

/** Debounced full recovery: force a fresh socket and re-fetch every
 * active/recent slice. Safe to call repeatedly/concurrently — a resume event
 * and the watchdog can fire close together, and this coalesces them into one
 * reconnect+rehydrate rather than racing two. */
export function resync() {
  if (resyncTimer) return
  resyncTimer = setTimeout(() => {
    resyncTimer = null
    if (resyncInFlight) return
    // Socket alive + data just hydrated (boot, or a resume seconds ago) —
    // nothing to recover; a focus/visibility flurry must not re-fetch
    // everything and churn the WS.
    if (useRadar.getState().connected && Date.now() - lastHydrateAt < RESYNC_MIN_FRESH_MS)
      return
    resyncInFlight = true
    useRadar.getState().setResyncing(true)
    forceReconnect()
    hydrate().finally(() => {
      resyncInFlight = false
      useRadar.getState().setResyncing(false)
    })
  }, RESYNC_DEBOUNCE_MS)
}

function startWatchdog() {
  if (watchdogStarted) return
  watchdogStarted = true
  // Backgrounded tabs throttle timers, which is fine here — the resume
  // listeners in lifecycle.ts cover recovery once the tab is foreground
  // again; this watchdog only needs to catch a zombie socket while the tab
  // stays in the foreground the whole time.
  setInterval(() => {
    if (Date.now() - lastMessageAt > STALE_MS) {
      useRadar.getState().setConnected(false)
      resync()
    }
  }, WATCHDOG_INTERVAL_MS)
}
