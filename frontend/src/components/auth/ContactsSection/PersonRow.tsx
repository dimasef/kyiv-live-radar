import type { ReactNode } from 'react'

import type { FriendUserBrief } from '@/api'
import Avatar from '@/components/common/Avatar'

import { personLabel } from './contactFormat'

/** Shared layout for a request row: avatar + name on the left, actions right. */
export default function PersonRow({
  user,
  children,
}: {
  user: FriendUserBrief
  children: ReactNode
}) {
  return (
    <li className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[13px] text-slate-300">
      <Avatar name={personLabel(user)} avatarUrl={user.avatar_url} size={28} />
      <span className="min-w-0 flex-1 truncate">{personLabel(user)}</span>
      {children}
    </li>
  )
}

export function IconBtn({
  onClick,
  label,
  className,
  children,
}: {
  onClick: () => void
  label: string
  className: string
  children: ReactNode
}) {
  return (
    <button onClick={onClick} aria-label={label} className={`flex-none rounded p-1 ${className}`}>
      {children}
    </button>
  )
}
