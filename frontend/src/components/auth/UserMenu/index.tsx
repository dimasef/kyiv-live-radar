import { UserRound } from 'lucide-react'
import { useState } from 'react'

import { type AuthUser } from '@/api'
import BottomSheet from '@/components/common/BottomSheet'
import { navigate } from '@/router'
import { useRadar } from '@/store'

import MenuBody from './MenuBody'

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
    <MenuBody
      user={user}
      label={label}
      gamification={gamification}
      pending={pending}
      go={go}
      onLogout={onLogout}
    />
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
          <BottomSheet onClose={close}>{body}</BottomSheet>
        </>
      )}
    </div>
  )
}
