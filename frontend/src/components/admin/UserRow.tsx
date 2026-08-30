import type { AdminUser } from '@/api'
import Avatar from '@/components/common/Avatar'
import { kyivStamp } from '@/lib/kyivTime'

import UserActions from './UserActions'
import UserBadges from './UserBadges'
import UserRoleSelect from './UserRoleSelect'
import { providerLabel, userLabel } from './userFormat'

const CELL = 'px-3 py-2 align-middle'

/** One account as a table row. A blocked one is dimmed rather than hidden — the
 * operator opens this tab right after blocking someone, to confirm it landed. */
export default function UserRow({
  user,
  currentUserId,
  onUpdated,
  onDeleted,
}: {
  user: AdminUser
  currentUserId: number | null | undefined
  onUpdated: (u: AdminUser) => void
  onDeleted: (id: number) => void
}) {
  const label = userLabel(user)

  return (
    <tr
      className={`border-t border-white/[0.06] hover:bg-white/[0.02] ${
        user.is_active ? '' : 'opacity-60'
      }`}
    >
      <td className={CELL}>
        <div className="flex items-center gap-2">
          <Avatar name={label} avatarUrl={user.avatar_url} size={28} />
          <div className="min-w-0">
            <div className="truncate text-slate-200">
              {label}
              {user.id === currentUserId && <span className="text-slate-500"> (ви)</span>}
            </div>
            {/* Skipped when the email IS the headline — a nameless account shows
                it as its name, and repeating it reads as two fields. */}
            {user.email && user.email !== label && (
              <div className="truncate text-[11px] text-slate-500">{user.email}</div>
            )}
          </div>
        </div>
      </td>
      <td className={CELL}>
        <UserRoleSelect user={user} currentUserId={currentUserId} onUpdated={onUpdated} />
      </td>
      <td className={CELL}>
        <UserBadges user={user} />
      </td>
      <td className={`${CELL} text-slate-400`}>
        {user.providers.map(providerLabel).join(', ') || '—'}
      </td>
      <td className={`${CELL} whitespace-nowrap text-slate-500`}>{kyivStamp(user.created_at)}</td>
      <td className={`${CELL} whitespace-nowrap text-slate-500`}>
        {kyivStamp(user.last_login_at)}
      </td>
      <td className={`${CELL} whitespace-nowrap text-slate-500`}>
        {kyivStamp(user.last_seen_at)}
      </td>
      <td className={`${CELL} text-right`}>
        <UserActions
          user={user}
          currentUserId={currentUserId}
          onUpdated={onUpdated}
          onDeleted={onDeleted}
        />
      </td>
    </tr>
  )
}
