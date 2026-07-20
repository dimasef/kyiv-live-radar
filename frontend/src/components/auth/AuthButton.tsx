import { LogIn, UserRound } from 'lucide-react'
import { useState } from 'react'

import { ACCOUNT_PATH, navigate } from '@/router'
import { useRadar } from '@/store'

import AuthModal from './AuthModal'

const pill =
  'flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] p-1.5 text-slate-400 transition-colors hover:border-white/20 hover:text-phosphor-soft md:px-2.5 md:py-1'

/** Header entry point: "Увійти" (opens the modal) when signed out, or the
 * account chip (→ /account) when signed in. Renders nothing while the boot
 * session refresh is still pending, to avoid a login-button flash. */
export default function AuthButton() {
  const [open, setOpen] = useState(false)
  const status = useRadar((s) => s.authStatus)
  const user = useRadar((s) => s.user)

  if (status === 'authed' && user) {
    const label = user.display_name || user.email || 'Акаунт'
    return (
      <button onClick={() => navigate(ACCOUNT_PATH)} className={pill} title={label}>
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="h-5 w-5 flex-none rounded-full" />
        ) : (
          <UserRound size={16} className="flex-none md:h-[13px] md:w-[13px]" />
        )}
        <span className="hidden max-w-[10ch] truncate font-mono text-[11px] md:inline">{label}</span>
      </button>
    )
  }

  if (status !== 'anon') return null

  return (
    <>
      <button onClick={() => setOpen(true)} className={pill} title="Увійти">
        <LogIn size={16} className="flex-none md:h-[13px] md:w-[13px]" />
        <span className="hidden font-mono text-[11px] md:inline">Увійти</span>
      </button>
      {open && <AuthModal onClose={() => setOpen(false)} />}
    </>
  )
}
