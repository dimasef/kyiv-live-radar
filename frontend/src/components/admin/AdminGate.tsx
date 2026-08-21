import { useState } from 'react'

import AuthModal from '@/components/auth/AuthModal'
import { isAdminRole } from '@/api'
import { useRadar } from '@/store'

/** Renders `children` only for an admin, with a sign-in prompt otherwise.
 *
 * UX only — the backend enforces the same thing with 401/403. The point of
 * gating here is that a non-admin never MOUNTS the data view, so none of its
 * fetches fire. Both admin surfaces (/admin and /raw) had this written out
 * verbatim; `prompt` is the only thing that differed between them. */
export default function AdminGate({
  prompt,
  children,
}: {
  prompt: string
  children: React.ReactNode
}) {
  const status = useRadar((s) => s.authStatus)
  const isAdmin = useRadar((s) => isAdminRole(s.user?.role))
  const [loginOpen, setLoginOpen] = useState(false)

  if (status === 'unknown') {
    return (
      <div className="flex h-full items-center justify-center bg-ink-950 text-xs text-slate-500">
        Завантаження…
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-ink-950 px-4 text-center text-slate-300">
        <p className="max-w-xs text-sm text-slate-400">
          {status === 'authed' ? 'Ця сторінка доступна лише адміністраторам.' : prompt}
        </p>
        {status !== 'authed' && (
          <button
            onClick={() => setLoginOpen(true)}
            className="rounded-lg bg-phosphor px-4 py-2 text-sm font-semibold text-ink-950 hover:opacity-90"
          >
            Увійти
          </button>
        )}
        {loginOpen && <AuthModal onClose={() => setLoginOpen(false)} />}
      </div>
    )
  }

  return <>{children}</>
}
