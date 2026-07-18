import { deletePushSubscribe, fetchPushConfig, postPushSubscribe } from '@/api'
import type { Home } from '@/store/homeSlice'

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

function toBody(sub: PushSubscription, home: Home | null) {
  const json = sub.toJSON()
  return {
    subscription: {
      endpoint: sub.endpoint,
      keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
    },
    home: home ? { lat: home.lat, lon: home.lon, radius_km: home.radiusKm } : null,
  }
}

/** Full opt-in flow. Must run from a user-gesture handler (iOS requires the
 * permission request inside one). Returns the resulting permission state. */
export async function subscribeHomePush(home: Home): Promise<NotificationPermission> {
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
  await postPushSubscribe(toBody(sub, home))
  return permission
}

/** Re-register the existing subscription (home moved / radius changed / app
 * boot) so the server's copy of the home zone never goes stale. No-op when the
 * browser holds no subscription. */
export async function resyncHomePush(home: Home | null): Promise<void> {
  const sub = await getBrowserSubscription()
  if (!sub) return
  await postPushSubscribe(toBody(sub, home))
}

export async function unsubscribeHomePush(): Promise<void> {
  const sub = await getBrowserSubscription()
  if (!sub) return
  await sub.unsubscribe()
  await deletePushSubscribe(sub.endpoint)
}
