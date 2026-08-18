/** Observer helpers that degrade instead of throwing.
 *
 * `new ResizeObserver(...)` / `new IntersectionObserver(...)` are a
 * ReferenceError on engines that lack them (TV browsers on old Chromium). Thrown
 * from a React effect that's exactly as fatal as a render error — the tree
 * unmounts and the screen goes black — so every construction goes through here.
 */

/** Call `onResize` when `el`'s box changes. Falls back to window resize +
 * orientation changes where ResizeObserver is missing: coarser, but it keeps the
 * layout self-correcting instead of crashing. Returns the cleanup. */
export function observeResize(el: Element, onResize: () => void): () => void {
  if (typeof ResizeObserver === 'function') {
    const ro = new ResizeObserver(onResize)
    ro.observe(el)
    return () => ro.disconnect()
  }
  window.addEventListener('resize', onResize)
  window.addEventListener('orientationchange', onResize)
  return () => {
    window.removeEventListener('resize', onResize)
    window.removeEventListener('orientationchange', onResize)
  }
}

/** Call `onVisible` when `el` scrolls into view. Where IntersectionObserver is
 * missing the caller simply never gets the callback (the feature it drives —
 * infinite scroll — degrades to whatever manual control exists). */
export function observeVisible(
  el: Element,
  onVisible: () => void,
  options?: IntersectionObserverInit,
): () => void {
  if (typeof IntersectionObserver !== 'function') return () => {}
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) onVisible()
  }, options)
  io.observe(el)
  return () => io.disconnect()
}
