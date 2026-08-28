import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** Collapses the desktop event-feed rail so the map gets the whole window.
 *
 * Desktop only (`hidden lg:flex`): on mobile the feed is the bottom sheet,
 * which already has its own handle and its own height settings.
 *
 * It rides the seam — pinned to the right edge of the MAP, so it sits against
 * the rail while the rail is there and slides to the window edge when it is
 * not. A control that moved somewhere else on collapse would be a control the
 * operator has to hunt for to undo what they just did.
 *
 * Half of it hangs over the map (`-mr-px` plus the rounded left corners) rather
 * than sitting inside the rail: the rail is unmounted when collapsed, so a
 * handle living inside it could not bring it back.
 */
export default function FeedToggle({ id }: { id: string }) {
  const { t } = useTranslation()
  const collapsed = useRadar((s) => s.feedCollapsed)
  const toggleFeed = useRadar((s) => s.toggleFeed)
  const Icon = collapsed ? ChevronLeft : ChevronRight

  return (
    <button
      onClick={toggleFeed}
      aria-label={t(collapsed ? 'log.show' : 'log.hide')}
      title={t(collapsed ? 'log.show' : 'log.hide')}
      aria-expanded={!collapsed}
      aria-controls={id}
      className="pointer-events-auto absolute right-0 top-1/2 z-[1000] hidden h-14 w-5 -translate-y-1/2 items-center justify-center rounded-l-md border border-r-0 border-white/10 bg-ink-900/85 text-slate-400 transition-colors hover:bg-ink-800 hover:text-phosphor-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-phosphor lg:flex"
    >
      <Icon size={14} aria-hidden />
    </button>
  )
}
