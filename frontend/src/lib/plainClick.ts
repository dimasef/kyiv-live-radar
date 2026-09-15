import type { MouseEvent } from 'react'

/** A click the app should handle itself, rather than let the browser take.
 *
 * Anything modified (new tab, new window, download) belongs to the browser —
 * intercepting those is how an in-app link loses the one thing that makes it a
 * link. `button !== 0` catches the middle click that opens a background tab. */
export function isPlainClick(e: MouseEvent): boolean {
  return !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && e.button === 0
}
