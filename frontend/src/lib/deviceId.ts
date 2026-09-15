import { STORAGE_KEYS, safeGet, safeSet } from './storage'

/** A stable id for THIS browser profile, minted once and kept in localStorage.
 *
 * The only thing that lets the admin console say anything at all about a reader
 * with no account: the websocket carries no identity, so without this every
 * reload of every anonymous tab is a new stranger and two tabs read as two
 * people. It identifies a browser profile and nothing more — clearing site data
 * makes the same person a new id, and the server never trusts it for anything
 * but grouping rows (see backend app/realtime/sessions.py).
 *
 * Private browsing and a storage-blocking browser both return null from
 * `safeGet`/refuse the write: those readers stay anonymous rows, which is the
 * honest answer rather than a failure.
 */
let cached: string | null = null

export function deviceId(): string {
  if (cached) return cached
  const stored = safeGet(STORAGE_KEYS.deviceId)
  cached = stored && stored.length <= 64 ? stored : newId()
  safeSet(STORAGE_KEYS.deviceId, cached)
  return cached
}

function newId(): string {
  // `crypto.randomUUID` needs a secure context and a browser newer than the
  // Samsung TV one this app supports, so it can genuinely be missing here.
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) return uuid
  return `d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
