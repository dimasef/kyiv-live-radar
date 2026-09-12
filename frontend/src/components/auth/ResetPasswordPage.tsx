import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api'
import { tokenFromSearch } from '@/router'
import { useRadar } from '@/store'

import EmailLinkPage from './EmailLinkPage'

/** `/reset-password?token=…` from the reset mail: a new password, then signed in. */
export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const resetPassword = useRadar((s) => s.resetPassword)
  const [token] = useState(tokenFromSearch)
  const [password, setPassword] = useState('')
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return
    setError(null)
    setState('busy')
    try {
      await resetPassword(token, password)
      setState('done')
    } catch (err) {
      setState('idle')
      if (err instanceof ApiError && err.status === 422) setError(t('auth.err.weakPassword'))
      else setError(t('auth.badToken'))
    }
  }

  return (
    <EmailLinkPage title={t('auth.resetTitle')} done={state === 'done'}>
      {!token ? (
        <p className="text-sm text-red-300">{t('auth.noToken')}</p>
      ) : state === 'done' ? (
        <p className="text-sm text-slate-300">{t('auth.resetDone')}</p>
      ) : (
        <form onSubmit={submit} className="space-y-2.5">
          <input
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-phosphor/40 focus:outline-none"
            type="password"
            required
            minLength={8}
            placeholder={t('auth.newPassword')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          {error && <p className="text-xs text-red-300">{error}</p>}
          <button
            type="submit"
            disabled={state === 'busy'}
            className="w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {state === 'busy' ? '…' : t('auth.setPassword')}
          </button>
        </form>
      )}
    </EmailLinkPage>
  )
}
