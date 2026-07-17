import { ChevronDown, ChevronUp } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

/** Collapses a long message: up to 5 lines show in full; anything longer is
 * clamped to 4 with a centred chevron to expand (and collapse) — no label.
 * Overflow depends on wrap width and is only knowable after layout, so it's
 * measured against the DOM and re-measured on resize; the chevron never appears
 * on text that already fits. */
export default function ClampText({
  text,
  className,
}: {
  text: string
  className?: string
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [long, setLong] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    // While expanded the clamp is off, so there's nothing to measure — keep the
    // last `long` value so the collapse chevron stays visible.
    if (!el || expanded) return
    const measure = () => setLong(el.scrollHeight > el.clientHeight + 1)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text, expanded])

  // 5 lines is the fits-in-full budget; once it overflows, collapse to 4 so the
  // chevron row sits where the 5th line would have been.
  const clamp = expanded ? '' : long ? 'line-clamp-4' : 'line-clamp-5'

  return (
    <>
      <div ref={ref} className={`${className ?? ''} ${clamp}`}>
        {text}
      </div>
      {(long || expanded) && (
        <div className="mt-1 flex justify-center">
          <button
            onClick={(e) => {
              e.stopPropagation()
              setExpanded((v) => !v)
            }}
            aria-label={t(expanded ? 'log.showLess' : 'log.showMore')}
            className="flex items-center justify-center rounded-full border border-white/15 px-2.5 py-0.5 text-slate-400 transition-colors hover:border-white/30 hover:bg-white/[0.04] hover:text-slate-200"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      )}
    </>
  )
}
