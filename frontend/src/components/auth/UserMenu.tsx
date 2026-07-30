import { Layers, LogOut, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { type AuthUser } from '@/api'
import Avatar from '@/components/common/Avatar'
import { APP_VERSION } from '@/changelog'
import { useDismissTransition } from '@/lib/useDismissTransition'
import { ACCOUNT_PATH, CHANGELOG_PATH, COLLECTION_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

const circle =
  'flex h-[40px] w-[40px] flex-none items-center justify-center overflow-hidden rounded-full border border-white/10 bg-white/[0.04] text-slate-400 transition-colors hover:border-white/20 hover:text-slate-100'

/** The signed-in user's navbar entry: the avatar opens a menu with the
 * account-scoped destinations (profile, collection) and sign-out. It's an
 * anchored dropdown on desktop and a bottom sheet on mobile. */
export default function UserMenu({ user }: { user: AuthUser }) {
  const [open, setOpen] = useState(false)
  const logout = useRadar((s) => s.logout)
  const gamification = useRadar((s) => s.gamification)
  const pending = useRadar((s) => s.friendRequests.incoming.length)

  const label = user.display_name || user.email || 'Акаунт'
  const close = () => setOpen(false)
  const go = (path: string) => {
    close()
    navigate(path)
  }
  const onLogout = () => {
    close()
    logout()
    navigate('/')
  }

  const body = (
    <MenuBody user={user} label={label} gamification={gamification} pending={pending} go={go} onLogout={onLogout} />
  )

  return (
    <div className="relative flex-none">
      <button
        onClick={() => setOpen((o) => !o)}
        className={circle}
        title={label}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <UserRound size={16} className="flex-none" />
        )}
      </button>
      {pending > 0 && (
        <span className="pointer-events-none absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold leading-none text-white ring-2 ring-ink-900">
          {pending > 9 ? '9+' : pending}
        </span>
      )}

      {open && (
        <>
          {/* Desktop: anchored dropdown (with a click-away layer). */}
          <div className="fixed inset-0 z-[1300] hidden sm:block" onClick={close} />
          <div
            role="menu"
            className="absolute right-0 top-full z-[1400] mt-2 hidden w-60 overflow-hidden rounded-xl border border-white/10 bg-ink-900 shadow-2xl sm:block"
          >
            {body}
          </div>

          {/* Mobile: bottom sheet. */}
          <MobileSheet onClose={close}>{body}</MobileSheet>
        </>
      )}
    </div>
  )
}

/** Slide-up bottom sheet for phones; a no-op visual on desktop (sm:hidden). */
function MobileSheet({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const { shown, close } = useDismissTransition(onClose)
  return createPortal(
    <div
      className={`fixed inset-0 z-[1400] flex flex-col justify-end bg-ink-950/70 backdrop-blur-sm transition-opacity duration-200 sm:hidden ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`rounded-t-2xl border-t border-white/10 bg-ink-900 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-2xl transition-transform duration-300 ease-out ${
          shown ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        <div className="mx-auto mt-2 mb-1 h-1 w-9 rounded-full bg-white/15" />
        {children}
      </div>
    </div>,
    document.body,
  )
}

function MenuBody({
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
        <Item icon={<UserRound size={15} />} onClick={() => go(ACCOUNT_PATH)} badge={pending || undefined}>
          Профіль
        </Item>
        {gamification && (
          <Item icon={<Layers size={15} />} onClick={() => go(COLLECTION_PATH)}>
            Колекція карток
          </Item>
        )}
      </div>

      <div className="border-t border-white/[0.06] py-1">
        <Item icon={<LogOut size={15} />} danger onClick={onLogout}>
          Вийти
        </Item>
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

function Item({
  icon,
  children,
  onClick,
  danger,
  badge,
}: {
  icon: ReactNode
  children: ReactNode
  onClick: () => void
  danger?: boolean
  badge?: number
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors ${
        danger ? 'text-red-300 hover:bg-red-400/[0.08]' : 'text-slate-300 hover:bg-white/[0.05] hover:text-slate-100'
      }`}
    >
      <span className="flex-none text-slate-500">{icon}</span>
      <span className="flex-1 text-left">{children}</span>
      {badge != null && badge > 0 && (
        <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
          {badge > 9 ? '9+' : badge}
        </span>
      )}
    </button>
  )
}
