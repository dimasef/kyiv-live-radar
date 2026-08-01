import { Layers, LogOut, UserRound } from 'lucide-react'

import { type AuthUser } from '@/api'
import { APP_VERSION } from '@/changelog'
import Avatar from '@/components/common/Avatar'
import { ACCOUNT_PATH, CHANGELOG_PATH, COLLECTION_PATH } from '@/router'

import MenuItem from './MenuItem'

/** Rendered by BOTH the desktop dropdown and the mobile sheet — that sharing is
 * the only reason it isn't inlined. */
export default function MenuBody({
  user,
  label,
  gamification,
  pending,
  go,
  onLogout,
}: {
  user: AuthUser
  label: string
  gamification: boolean
  pending: number
  go: (path: string) => void
  onLogout: () => void
}) {
  return (
    <>
      <div className="flex items-center gap-3 border-b border-white/[0.06] px-3.5 py-3">
        <Avatar name={label} avatarUrl={user.avatar_url} size={38} />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-100">{label}</p>
          {user.email && <p className="truncate text-[11px] text-slate-500">{user.email}</p>}
        </div>
      </div>

      <div className="py-1">
        <MenuItem icon={<UserRound size={15} />} onClick={() => go(ACCOUNT_PATH)} badge={pending || undefined}>
          Профіль
        </MenuItem>
        {gamification && (
          <MenuItem icon={<Layers size={15} />} onClick={() => go(COLLECTION_PATH)}>
            Колекція карток
          </MenuItem>
        )}
      </div>

      <div className="border-t border-white/[0.06] py-1">
        <MenuItem icon={<LogOut size={15} />} danger onClick={onLogout}>
          Вийти
        </MenuItem>
      </div>

      <button
        onClick={() => go(CHANGELOG_PATH)}
        className="flex w-full items-center justify-center gap-1 border-t border-white/[0.06] px-3.5 py-2 font-mono text-[11px] text-slate-500 transition-colors hover:text-slate-300"
      >
        v{APP_VERSION}
      </button>
    </>
  )
}
