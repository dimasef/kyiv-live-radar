import { useCallback, useEffect, useRef, useState } from 'react'

/** Enter/leave transition for a conditionally-mounted overlay (modal/drawer):
 * mounts off-screen, transitions in next frame, and on close() plays the leave
 * transition before invoking onClose (which unmounts). Drive Tailwind
 * transition classes off the returned `shown`. */
export function useDismissTransition(onClose: () => void, ms = 220) {
  const [shown, setShown] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const raf = requestAnimationFrame(() => setShown(true))
    return () => {
      cancelAnimationFrame(raf)
      if (timer.current) clearTimeout(timer.current)
    }
  }, [])

  const close = useCallback(() => {
    setShown(false)
    timer.current = setTimeout(onClose, ms)
  }, [onClose, ms])

  return { shown, close }
}
