import type { AdminUser } from '@/api'

const CHIP = 'rounded px-1.5 py-0.5 text-[10px] leading-4 border whitespace-nowrap'

/** The «Стан» cell: only what's WRONG with an account. Role and sign-in methods
 * have columns of their own, so repeating them here would just make every row
 * carry four chips that say nothing. A healthy account shows a dash. */
export default function UserBadges({ user }: { user: AdminUser }) {
  const flags = []

  if (!user.is_active) {
    flags.push(
      <span key="blocked" className={`${CHIP} border-rose-500/40 bg-rose-500/10 text-rose-300`}>
        заблокований
      </span>,
    )
  }

  if (user.email && !user.email_verified) {
    flags.push(
      <span
        key="unverified"
        title="Email не підтверджений жодним провайдером — він не рахується для видачі адмінки зі списку ADMIN_EMAILS."
        className={`${CHIP} border-white/10 bg-white/[0.04] text-slate-500`}
      >
        email не підтв.
      </span>,
    )
  }

  if (flags.length === 0) return <span className="text-slate-700">—</span>
  return <div className="flex flex-wrap gap-1">{flags}</div>
}
