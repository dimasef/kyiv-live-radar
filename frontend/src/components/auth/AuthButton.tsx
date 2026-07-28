import { LogIn, UserRound } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ACCOUNT_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

import AuthModal from './AuthModal'

const circle =
  'flex h-[40px] w-[40px] flex-none items-center justify-center overflow-hidden rounded-full border border-white/10 bg-white/[0.04] text-slate-400 transition-colors hover:border-white/20 hover:text-slate-100'
const pill =
  'flex h-[40px] w-[40px] items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-400 transition-colors hover:border-white/20 hover:text-slate-100 md:w-auto md:justify-start md:gap-1.5 md:px-2.5'

/** Navbar entry point: the account avatar (→ /account) when signed in, or a
 * "Sign in" button (opens the modal) when signed out. Renders nothing while the
 * boot session refresh is still pending, to avoid a login-button flash. */
export default function AuthButton() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const status = useRadar((s) => s.authStatus)
  const user = useRadar((s) => s.user)
  const requests = useRadar((s) => s.friendRequests)

  if (status === 'authed' && user) {
    const label = user.display_name || user.email || t('auth.account')
    // Pending incoming contact requests → a red badge on the avatar, since
    // there's no other notification surface for them (managed on /account).
    const pending = requests.incoming.length
    const badgeLabel = pending > 0 ? `${label} · ${t('friends.incoming')}: ${pending}` : label
    return (
      // Wrapper so the badge can escape the button's overflow-hidden clip.
      <div className="relative flex-none">
        <button
          onClick={() => navigate(ACCOUNT_PATH)}
          className={circle}
          title={badgeLabel}
          aria-label={badgeLabel}
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
      </div>
    )
  }

  if (status !== 'anon') return null

  return (
    <>
      <button onClick={() => setOpen(true)} className={pill} title={t('auth.signIn')}>
        <LogIn size={16} className="flex-none" />
        <span className="hidden font-mono text-[11px] md:inline">{t('auth.signIn')}</span>
      </button>
      {open && <AuthModal onClose={() => setOpen(false)} />}
    </>
  )
}
