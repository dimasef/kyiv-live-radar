/// <reference lib="webworker" />
import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkOnly } from 'workbox-strategies'

// Hand-written SW (injectManifest) — see vite.config.ts. Excluded from the app
// `tsc -b` project (uses webworker globals); vite-plugin-pwa bundles it.
declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{ url: string; revision: string | null }> }

// Precache the built app shell (JS/CSS/HTML/icons) — Workbox fills __WB_MANIFEST
// at build time.
precacheAndRoute(self.__WB_MANIFEST)

// SPA navigation fallback: same-origin navigations serve the cached index.html
// shell. The app then hydrates live data over the network (never from cache).
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html')))

// Defence-in-depth — THE safety invariant. The backend (threats / alerts / WS)
// is a SEPARATE origin, so Workbox never caches it by default; pin it NetworkOnly
// anyway so no future runtime rule can ever serve a stale all-clear or threat
// from cache. A cached "відбій" during a real attack is exactly what this app
// must never do.
const API_ORIGIN = (() => {
  try {
    return new URL(import.meta.env.VITE_API_URL ?? '').origin
  } catch {
    return ''
  }
})()
if (API_ORIGIN) {
  registerRoute(({ url }) => url.origin === API_ORIGIN, new NetworkOnly())
}

// registerType 'prompt': the update toast (UpdateToast.tsx) posts SKIP_WAITING
// when the user accepts, activating the freshly-installed SW.
self.addEventListener('message', (e) => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting()
})

// --- Stage B (Web Push) mounts here — see .claude/plans/pwa.md ---
// self.addEventListener('push', (e) => { /* showNotification(...) */ })
// self.addEventListener('notificationclick', (e) => { /* clients.openWindow('/') */ })
