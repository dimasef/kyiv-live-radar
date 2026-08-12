import type { BugContext } from '@/api'
import { APP_VERSION } from '@/changelog'

/** Everything a bug report should carry that a person shouldn't have to type.
 *
 * The list is the one the 2026-08-12 Android investigation wished it had: the
 * app version, what it was running in, and the three numbers that describe the
 * viewport — its size, the device pixel ratio, and the page scale. That last
 * one WAS the bug (Chrome had zoomed the page to its 0.25 floor), and no
 * screenshot can show it.
 */
export function collectClientContext(): BugContext {
  const vv = window.visualViewport
  return {
    app_version: APP_VERSION,
    route: window.location.pathname,
    user_agent: navigator.userAgent.slice(0, 1000),
    viewport_w: window.innerWidth,
    viewport_h: window.innerHeight,
    dpr: round2(window.devicePixelRatio),
    scale: vv ? round2(vv.scale) : null,
    standalone: window.matchMedia('(display-mode: standalone)').matches,
    language: navigator.language,
    online: navigator.onLine,
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}
