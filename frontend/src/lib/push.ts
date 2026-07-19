import { deletePushSubscribe, fetchPushConfig, postPushSubscribe } from '@/api'
import type { Home } from '@/store/homeSlice'
import type { NotifyPrefs } from '@/store/notifySlice'

/** Browser side of Web Push for danger-near-home: permission + PushManager
 * subscription + registering it (with the home zone) on the backend. The
 * server assesses every track against the registered home and pushes on
 * escalation — see backend app/pipeline/home_push.py. */

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

export const pushSupported = () =>
  'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

export async function getBrowserSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null
  const reg = await navigator.serviceWorker.ready
  return reg.pushManager.getSubscription()
}

/** UI prefs -> the backend wire shape: the single "drone" toggle covers both
 * drone target types; `unknown` is never sent — the server always lets it
 * through (an untyped track must not be silently filtered). */
function wirePrefs(prefs: NotifyPrefs) {
  const types: string[] = []
  if (prefs.ballistic) types.push('ballistic')
  if (prefs.missile) types.push('missile')
  if (prefs.drone) types.push('shahed', 'jet_drone')
  return { min_level: prefs.minLevel, types, citywide: prefs.citywide }
}

function toBody(sub: PushSubscription, home: Home | null, prefs: NotifyPrefs) {
  const json = sub.toJSON()
  return {
    subscription: {
      endpoint: sub.endpoint,
      keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
    },
    home: home ? { lat: home.lat, lon: home.lon, radius_km: home.radiusKm } : null,
    prefs: wirePrefs(prefs),
  }
}

/** Full opt-in flow. Must run from a user-gesture handler (iOS requires the
 * permission request inside one). Returns the resulting permission state. */
export async function subscribeHomePush(
  home: Home,
  prefs: NotifyPrefs,
): Promise<NotificationPermission> {
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission
  const config = await fetchPushConfig()
  if (!config.enabled || !config.public_key) throw new Error('push not configured')
  const reg = await navigator.serviceWorker.ready
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.public_key),
    }))
  await postPushSubscribe(toBody(sub, home, prefs))
  return permission
}

/** Re-register the existing subscription (home moved / prefs changed / app
 * boot) so the server's copy never goes stale. No-op when the browser holds
 * no subscription. */
export async function resyncHomePush(home: Home | null, prefs: NotifyPrefs): Promise<void> {
  const sub = await getBrowserSubscription()
  if (!sub) return
  await postPushSubscribe(toBody(sub, home, prefs))
}

export async function unsubscribeHomePush(): Promise<void> {
  const sub = await getBrowserSubscription()
  if (!sub) return
  await sub.unsubscribe()
  await deletePushSubscribe(sub.endpoint)
}
