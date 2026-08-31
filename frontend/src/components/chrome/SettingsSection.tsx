import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/** One block of the settings drawer: bordered card, icon + caps title, and
 * whatever the block is about underneath.
 *
 * Extracted because the seven blocks each rebuilt this by hand and drifted —
 * two icon placements (inside the title vs beside it), two header gaps, two
 * inter-section margins, and one block with no icon at all. The gap BETWEEN
 * sections belongs to the drawer's `space-y`, not here, so a hidden section
 * (signed out, unsupported browser) cannot leave a margin behind.
 */
export default function SettingsSection({
  icon: Icon,
  title,
  action,
  children,
}: {
  icon: LucideIcon
  title: string
  /** Right-hand side of the header — a switch, a reset link, a dismiss button. */
  action?: ReactNode
  children?: ReactNode
}) {
  return (
    <section className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className={`flex items-center justify-between gap-3 ${children ? 'mb-2.5' : ''}`}>
        <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Icon size={13} className="flex-none text-phosphor-soft/80" />
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  )
}
