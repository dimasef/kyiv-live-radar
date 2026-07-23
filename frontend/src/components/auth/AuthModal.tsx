import { Eye, EyeOff, X } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api'
import { useDismissTransition } from '@/lib/useDismissTransition'
import { useRadar } from '@/store'

import GoogleButton from './GoogleButton'
import TelegramButton from './TelegramButton'

type Mode = 'login' | 'register'

const HAS_SSO = Boolean(
  import.meta.env.VITE_GOOGLE_CLIENT_ID || import.meta.env.VITE_TELEGRAM_LOGIN_BOT,
)

/** Email/password sign-in + registration, with the SSO buttons on top. Mounted
 * only while open, so it animates in and out; closes itself on success. */
export default function AuthModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const login = useRadar((s) => s.login)
  const register = useRadar((s) => s.register)

  const errorMessage = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 401) return t('auth.err.badCredentials')
      if (err.status === 400) return t('auth.err.emailTaken')
      if (err.status === 422) return t('auth.err.weakPassword')
      if (err.status === 503) return t('auth.err.unavailable')
    }
    return mode === 'login' ? t('auth.err.loginFailed') : t('auth.err.registerFailed')
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'login') await login(email.trim().toLowerCase(), password)
      else await register(email.trim().toLowerCase(), password, name.trim() || undefined)
      close()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-phosphor/40 focus:outline-none'

  // Portal to <body>: the Header's backdrop-filter would otherwise make it the
  // containing block for this `fixed` overlay, trapping the modal inside the
  // header instead of covering the viewport.
  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        className={`w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl transition-all duration-200 ease-out ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-base font-bold text-slate-100">
            {mode === 'login' ? t('auth.loginTitle') : t('auth.registerTitle')}
          </h2>
          <button onClick={close} className="text-slate-400 hover:text-slate-200" aria-label={t('auth.close')}>
            <X size={18} />
          </button>
        </div>

        {HAS_SSO && (
          <>
            <div className="space-y-2">
              <GoogleButton onError={() => setError(t('auth.err.googleFailed'))} />
              <TelegramButton onError={() => setError(t('auth.err.telegramFailed'))} />
            </div>
            <div className="my-4 flex items-center gap-3 text-[11px] text-slate-600">
              <span className="h-px flex-1 bg-white/10" />
              {t('auth.or')}
              <span className="h-px flex-1 bg-white/10" />
            </div>
          </>
        )}

        <form onSubmit={submit} className="space-y-2.5">
          {mode === 'register' && (
            <input
              className={input}
              placeholder={t('auth.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          )}
          <input
            className={input}
            type="email"
            required
            placeholder={t('auth.email')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <div className="relative">
            <input
              className={`${input} pr-10`}
              type={showPassword ? 'text' : 'password'}
              required
              minLength={mode === 'register' ? 8 : undefined}
              placeholder={t('auth.password')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 transition-colors hover:text-slate-200"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {error && <p className="text-xs text-red-300">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? '…' : mode === 'login' ? t('auth.signIn') : t('auth.register')}
          </button>
        </form>

        <p className="mt-3 text-center text-xs text-slate-400">
          {mode === 'login' ? t('auth.noAccount') : t('auth.haveAccount')}{' '}
          <button
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError(null)
            }}
            className="text-phosphor-soft underline underline-offset-2 transition-colors hover:text-phosphor"
          >
            {mode === 'login' ? t('auth.register') : t('auth.signIn')}
          </button>
        </p>
      </div>
    </div>,
    document.body,
  )
}
