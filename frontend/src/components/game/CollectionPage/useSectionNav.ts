import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

/** How far below the sticky bar the probe line sits: a section counts as
 * current once its header has climbed to just under the bar. */
const PROBE_PX = 24
/** Scroll events stop when a programmatic smooth scroll lands; this long
 * without one means it has. */
const SETTLE_MS = 150

/** Scroll-spy plus jump-to for the collection's rarity sections.
 *
 * `active` is the last section whose top has passed the probe line under the
 * sticky bar — or the last section of all once the container is scrolled to
 * the bottom, since a short final section may never reach the line on a tall
 * screen. A click pins its section until the reader scrolls again: the
 * smooth scroll would otherwise flicker the pills through every section it
 * passes, and a jump that can't scroll far enough would land on a neighbour.
 *
 * The scroller is taken through a callback ref, not a ref object: the page
 * renders a placeholder until the collection is allowed to show, so the
 * element does not exist on the first commit and a mount-time effect would
 * never see it. Plain scroll events on purpose, not IntersectionObserver:
 * they work on every engine the app targets (see lib/observers). */
export function useSectionNav(
  sticky: RefObject<HTMLElement | null>,
  ids: readonly string[],
): { active: string | null; jumpTo: (id: string) => void; scrollerRef: (el: HTMLElement | null) => void } {
  const [scroller, setScroller] = useState<HTMLElement | null>(null)
  const [active, setActive] = useState<string | null>(ids[0] ?? null)
  const pinned = useRef(false)
  const settle = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const el = scroller
    if (!el) return
    let raf = 0

    const measure = () => {
      raf = 0
      const line = el.getBoundingClientRect().top + (sticky.current?.offsetHeight ?? 0) + PROBE_PX
      let current = ids[0] ?? null
      for (const id of ids) {
        const section = document.getElementById(id)
        if (section && section.getBoundingClientRect().top <= line) current = id
      }
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 2) current = ids[ids.length - 1] ?? null
      setActive(current)
    }

    const onScroll = () => {
      if (pinned.current) {
        if (settle.current) clearTimeout(settle.current)
        settle.current = setTimeout(() => {
          pinned.current = false
        }, SETTLE_MS)
        return
      }
      if (!raf) raf = requestAnimationFrame(measure)
    }

    el.addEventListener('scroll', onScroll, { passive: true })
    measure()
    return () => {
      el.removeEventListener('scroll', onScroll)
      if (raf) cancelAnimationFrame(raf)
      if (settle.current) clearTimeout(settle.current)
    }
  }, [scroller, sticky, ids])

  const jumpTo = useCallback(
    (id: string) => {
      const section = document.getElementById(id)
      if (!scroller || !section) return
      const top =
        section.getBoundingClientRect().top -
        scroller.getBoundingClientRect().top +
        scroller.scrollTop -
        (sticky.current?.offsetHeight ?? 0)
      pinned.current = true
      setActive(id)
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      try {
        scroller.scrollTo({ top, behavior: reduced ? 'auto' : 'smooth' })
      } catch {
        scroller.scrollTop = top
      }
    },
    [scroller, sticky],
  )

  return { active, jumpTo, scrollerRef: setScroller }
}
