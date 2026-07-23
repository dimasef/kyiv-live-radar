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

  if (status === 'authed' && user) {
    const label = user.display_name || user.email || t('auth.account')
    return (
      <button
        onClick={() => navigate(ACCOUNT_PATH)}
        className={circle}
        title={label}
        aria-label={label}
      >
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <UserRound size={16} className="flex-none" />
        )}
      </button>
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
