import { Check, Loader2, Pencil, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { AuthUser } from '@/api'
import { useRadar } from '@/store'

import AvatarPicker from './AvatarPicker'

/** Display names longer than this just truncate in contact rows and map
 * tooltips. Mirrors DISPLAY_NAME_MAX in backend app/schemas/auth.py — the
 * server is the one that enforces it; this only stops the typing. */
const NAME_MAX = 25

const ROLE_BADGE: Record<string, { label: string; cls: string; shield: boolean }> = {
  admin_g: { label: 'Дівчина Адміна', cls: 'bg-pink-400/15 text-pink-300', shield: true },
  admin: { label: 'Адміністратор', cls: 'bg-phosphor/15 text-phosphor-soft', shield: true },
  user: { label: 'Користувач', cls: 'bg-white/5 text-slate-400', shield: false },
}

/** Who you are: picture, name, email, role — and a pencil that turns the first
 * two into editable controls.
 *
 * One edit mode drives both, rather than each field owning its own affordance:
 * the avatar's camera/bin appear over the picture, the name becomes an input.
 * The name is committed explicitly (✓); the avatar commits as soon as its own
 * dialog is confirmed, since cropping and deleting already ask in their own
 * right and a second confirmation on top would just be noise. */
export default function IdentityCard({ user }: { user: AuthUser }) {
  const { t } = useTranslation()
  const updateProfile = useRadar((s) => s.updateProfile)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const fallbackName = user.display_name || user.email || 'Акаунт'
  const role = ROLE_BADGE[user.role] ?? ROLE_BADGE.user

  const startEditing = () => {
    setDraft(user.display_name ?? '')
    setEditing(true)
  }

  const commit = async () => {
    const next = draft.trim()
    if (next === (user.display_name ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      // Empty clears the name — the UI then falls back to the email, the same
      // way an absent avatar falls back to a monogram.
      await updateProfile({ display_name: next || null })
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="panel flex items-center gap-4 p-4">
      <AvatarPicker name={fallbackName} editing={editing} size={80} />

      <div className="min-w-0 flex-1">
        {editing ? (
          <>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void commit()
                if (e.key === 'Escape') setEditing(false)
              }}
              maxLength={NAME_MAX}
              autoFocus
              placeholder={t('profile.namePlaceholder')}
              className="w-full rounded-lg border border-white/15 bg-ink-950 px-2.5 py-1.5 text-base text-slate-100 outline-none focus:border-phosphor/40"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              {draft.length}/{NAME_MAX}
            </p>
          </>
        ) : (
          <h1 className="truncate font-display text-lg font-bold text-slate-100">{fallbackName}</h1>
        )}
        {user.email && !editing && (
          <p className="truncate text-xs text-slate-500">{user.email}</p>
        )}
        <span
          className={`mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${role.cls}`}
        >
          {role.shield && <ShieldCheck size={11} />}
          {role.label}
        </span>
      </div>

      {/* A real flex column rather than an absolute overlay: positioned
          absolutely, these sat ON TOP of the name input, which spans the middle
          column's full width. `self-start` keeps them in the top-right corner
          while still taking up layout space. */}
      <div className="flex flex-none items-center gap-1 self-start">
        {editing ? (
          <>
            <button
              onClick={() => setEditing(false)}
              disabled={saving}
              aria-label={t('profile.cancel')}
              title={t('profile.cancel')}
              className="flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/10 hover:text-slate-100"
            >
              <X size={14} />
            </button>
            <button
              onClick={() => void commit()}
              disabled={saving}
              aria-label={t('profile.save')}
              title={t('profile.save')}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-phosphor/20 text-phosphor-soft transition-colors hover:bg-phosphor/30"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            </button>
          </>
        ) : (
          <button
            onClick={startEditing}
            aria-label={t('profile.edit')}
            title={t('profile.edit')}
            className="flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/10 hover:text-slate-100"
          >
            <Pencil size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
