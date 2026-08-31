import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

/** A settings row that leads somewhere — a modal, a page. One look for all
 * three of them: the marker editor, the changelog and the bug report, which
 * used to be a bordered card, a bare row with a 13px chevron and a bare row
 * with a 15px one.
 *
 * Renders as an anchor when given an `href`, so a destination with a real URL
 * (the changelog) stays middle-clickable and shareable while still behaving
 * like the rest of the list.
 */
export default function SettingsRow({
  icon,
  label,
  sub,
  right,
  href,
  onClick,
}: {
  /** Any node, not just a lucide icon — the marker row shows its own glyph. */
  icon?: ReactNode
  label: string
  sub?: string
  /** Shown just before the chevron (the version number). */
  right?: ReactNode
  href?: string
  onClick: () => void
}) {
  const className =
    'group flex w-full items-center gap-2.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-left transition-colors duration-200 hover:border-white/20 hover:bg-white/[0.06]'
  const inner = (
    <>
      {icon}
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-slate-200">{label}</span>
        {sub && <span className="block truncate text-sm text-slate-500">{sub}</span>}
      </span>
      {right}
      <ChevronRight
        size={13}
        className="flex-none text-slate-500 transition-colors group-hover:text-slate-300"
      />
    </>
  )

  if (href) {
    return (
      <a
        href={href}
        onClick={(e) => {
          e.preventDefault()
          onClick()
        }}
        className={className}
      >
        {inner}
      </a>
    )
  }
  return (
    <button onClick={onClick} className={className}>
      {inner}
    </button>
  )
}
