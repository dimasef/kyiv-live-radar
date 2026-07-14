import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'

export default function Presence({ visible, children }: { visible: boolean; children: ReactNode }) {
  const [mounted, setMounted] = useState(visible)
  const last = useRef<ReactNode>(children)
  if (visible) last.current = children

  useEffect(() => {
    if (visible) {
      setMounted(true)
      return
    }
    const id = setTimeout(() => setMounted(false), 260)
    return () => clearTimeout(id)
  }, [visible])

  if (!mounted) return null

  return (
    <div className={`flex w-full justify-center ${visible ? 'banner-enter' : 'banner-leave'}`}>
      {last.current}
    </div>
  )
}
