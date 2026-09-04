import { useState } from 'react'

import { type AdminUser, type AssignableRole, setUserRole } from '@/api'

import { ROLE_BLOCKED_TEXT, roleChangeBlockedReason, roleLabel } from './userFormat'

const OPTIONS: { value: AssignableRole; label: string }[] = [
  { value: 'user', label: 'Користувач' },
  { value: 'observer', label: 'Спостерігач' },
  { value: 'admin_g', label: 'Адмін' },
]

/** Placeholder value for a role the select can DISPLAY but not assign. It must
 * not collide with a real option: sharing 'user' would mean picking «Користувач»
 * doesn't change the select's value, so onChange never fires and the demotion
 * silently does nothing. */
const STALE = '__derived__'
const CURRENT: Record<AdminUser['role'], string> = {
  user: 'user',
  observer: 'observer',
  admin_g: 'admin_g',
  admin: STALE,
}

/** The role cell: a dropdown where the role is ours to set, plain text where it
 * isn't.
 *
 * Only two values are assignable. Plain 'admin' is derived from the env
 * allowlists on every login, so it can be displayed but never chosen — picking
 * it would either change nothing or silently revert at the next sign-in. */
export default function UserRoleSelect({
  user,
  currentUserId,
  onUpdated,
}: {
  user: AdminUser
  currentUserId: number | null | undefined
  onUpdated: (u: AdminUser) => void
}) {
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)
  const label = roleLabel(user)
  const blocked = roleChangeBlockedReason(user, currentUserId)

  if (blocked) {
    return (
      <span
        title={ROLE_BLOCKED_TEXT[blocked]}
        className={`text-xs ${label.stale ? 'text-amber-300' : 'text-slate-400'}`}
      >
        {label.text}
        {blocked === 'allowlist' && <span className="text-slate-600"> (env)</span>}
      </span>
    )
  }

  const change = (role: AssignableRole) => {
    setPending(true)
    setFailed(false)
    setUserRole(user.id, role)
      .then(onUpdated)
      .catch(() => setFailed(true))
      .finally(() => setPending(false))
  }

  return (
    <div className="flex items-center gap-1">
      <select
        value={CURRENT[user.role]}
        disabled={pending}
        title={label.title}
        onChange={(e) => e.target.value !== STALE && change(e.target.value as AssignableRole)}
        className={`rounded-md border bg-ink-950 px-1.5 py-1 text-xs disabled:opacity-40 ${
          failed
            ? 'border-rose-500/40 text-rose-300'
            : label.stale
              ? 'border-amber-500/40 text-amber-300'
              : 'border-white/15 text-slate-300'
        }`}
      >
        {/* A stale 'admin' is neither assignable value, so name it explicitly
            rather than letting the select silently show 'Користувач'. */}
        {user.role === 'admin' && (
          <option value={STALE} disabled>
            Адмін (втрачає роль)
          </option>
        )}
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {label.stale && <span title={label.title}>⚠</span>}
    </div>
  )
}
