import { useRadar } from './store'
import { fetchSync } from './api'
import { applySnapshot, feedPage, hydrate, lastHydrateAt } from './store/bootstrap'
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
// Where in the server's frame stream this client is (see WSCommon). Null until
// the first frame — the very first connect still does a full hydrate.
let streamEpoch: number | null = null
let streamSeq: number | null = null
let resumeInFlight: { promise: Promise<void>; startedAt: number } | null = null
const RESUME_COALESCE_MS = 2_000
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
    // Catch up on what was missed while disconnected: the exact frames when
    // the server still has them, one snapshot otherwise (see resumeStream).
    void resumeStream()
  }

  socket.onmessage = (e) => {
    lastMessageAt = Date.now()
    try {
      applyFrame(JSON.parse(e.data) as WSMessage)
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
    // Full jitter: a deploy drops every socket at the same instant, and without
    // it every reader retries in lockstep — N boots (13 requests each) landing
    // on the backend in the same second, wave after wave.
    const base = 500 * 2 ** retry
    reconnectTimer = setTimeout(connectWS, base / 2 + Math.random() * base)
  }

  socket.onclose = scheduleReconnect
  socket.onerror = () => socket?.close()

  startWatchdog()
}

function applyFrame(msg: WSMessage) {
  if (msg.epoch != null && msg.seq != null) {
    streamEpoch = msg.epoch
    streamSeq = msg.seq
  }
  useRadar.getState().handleWS(msg)
}

/** Bring the store up to date after a (re)connect with ONE request instead of
 * the ten `hydrate()` fires. Every open tab reconnects in the same second
 * after a deploy, so this is what keeps that second survivable. Falls back to
 * the full hydrate whenever the server cannot answer. */
export function resumeStream(): Promise<void> {
  if (resumeInFlight && Date.now() - resumeInFlight.startedAt < RESUME_COALESCE_MS)
    return resumeInFlight.promise
  const promise = runResume().finally(() => {
    if (resumeInFlight?.promise === promise) resumeInFlight = null
  })
  resumeInFlight = { promise, startedAt: Date.now() }
  return promise
}

async function runResume(): Promise<void> {
  if (streamEpoch == null || streamSeq == null) return hydrate()
  const page = feedPage()
  let result
  try {
    result = await fetchSync(streamEpoch, streamSeq, page.limit, page.regions)
  } catch {
    return hydrate()
  }
  switch (result.status) {
    case 'current':
      return
    case 'delta':
      // Live frames may already have overtaken the replay on the fresh
      // socket; a replayed frame older than the newest applied one would
      // roll a track back, so only what is genuinely still ahead is applied.
      for (const frame of result.frames as WSMessage[]) {
        if (frame.epoch === streamEpoch && frame.seq != null && frame.seq <= (streamSeq ?? -1))
          continue
        applyFrame(frame)
      }
      return
    case 'full':
      if (result.snapshot) applySnapshot(result.snapshot)
      streamEpoch = result.epoch
      streamSeq = result.seq
      return
  }
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
    resumeStream().finally(() => {
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
