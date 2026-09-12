import { Eye, EyeOff, X } from 'lucide-react'
import { type FormEvent, useCallback, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { ApiError, authForgotPassword, authResendVerification } from '@/api'
import { useDismissTransition } from '@/lib/useDismissTransition'
import { useRadar } from '@/store'

import GoogleButton from './GoogleButton'

type Mode = 'login' | 'register' | 'forgot'
/** After a submit that only sends mail, the form gives way to a notice. */
type Sent = 'verification' | 'reset' | null

const HAS_SSO = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID)

const INPUT =
  'w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-phosphor/40 focus:outline-none'
const PRIMARY =
  'w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50'
const LINK = 'text-phosphor-soft underline underline-offset-2 transition-colors hover:text-phosphor'

/** Email/password sign-in, registration and password reset, with Google on
 * top. Registration and reset only send mail: the modal then shows where the
 * link went and stays open until dismissed. Sign-in closes it on success. */
export default function AuthModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)
  const [mode, setMode] = useState<Mode>('login')
  const [sent, setSent] = useState<Sent>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unverified, setUnverified] = useState(false)
  const [resent, setResent] = useState(false)
  const [busy, setBusy] = useState(false)
  const login = useRadar((s) => s.login)
  const register = useRadar((s) => s.register)

  // Stable on purpose: GoogleButton lists `onError` in the dep array of the
  // effect that renders Google's widget, so an inline arrow would re-run
  // renderButton on every keystroke in the email field.
  const onGoogleError = useCallback(() => setError(t('auth.err.googleFailed')), [t])

  const cleanEmail = () => email.trim().toLowerCase()

  const switchMode = (next: Mode) => {
    setMode(next)
    setSent(null)
    setError(null)
    setUnverified(false)
    setResent(false)
  }

  const errorMessage = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 401) return t('auth.err.badCredentials')
      if (err.status === 400) return t('auth.err.emailTaken')
      if (err.status === 422) return t('auth.err.weakPassword')
      if (err.status === 429) return t('auth.err.tooMany')
      if (err.status === 503) return mode === 'login' ? t('auth.err.unavailable') : t('auth.err.mail')
    }
    if (mode === 'login') return t('auth.err.loginFailed')
    if (mode === 'register') return t('auth.err.registerFailed')
    return t('auth.err.mail')
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setUnverified(false)
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(cleanEmail(), password)
        close()
      } else if (mode === 'register') {
        await register(cleanEmail(), password, name.trim() || undefined)
        setSent('verification')
      } else {
        await authForgotPassword(cleanEmail())
        setSent('reset')
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'email_unverified') setUnverified(true)
      else setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setBusy(true)
    try {
      await authResendVerification(cleanEmail())
      setResent(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const title =
    sent === 'verification'
      ? t('auth.registerSentTitle')
      : mode === 'login'
        ? t('auth.loginTitle')
        : mode === 'register'
          ? t('auth.registerTitle')
          : t('auth.forgotTitle')

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
          <h2 className="font-display text-base font-bold text-slate-100">{title}</h2>
          <button onClick={close} className="text-slate-400 hover:text-slate-200" aria-label={t('auth.close')}>
            <X size={18} />
          </button>
        </div>

        {sent ? (
          <div className="space-y-3 text-sm text-slate-300">
            <p>{t(sent === 'verification' ? 'auth.registerSent' : 'auth.resetSent', { email: cleanEmail() })}</p>
            {sent === 'verification' && (
              <button type="button" onClick={resend} disabled={busy || resent} className={`text-xs ${LINK}`}>
                {resent ? t('auth.resent') : t('auth.resend')}
              </button>
            )}
            {error && <p className="text-xs text-red-300">{error}</p>}
            <button type="button" onClick={close} className={PRIMARY}>
              {t('auth.close')}
            </button>
          </div>
        ) : (
          <>
            {HAS_SSO && mode !== 'forgot' && (
              <>
                <GoogleButton onError={onGoogleError} />
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
                  className={INPUT}
                  placeholder={t('auth.name')}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                />
              )}
              <input
                className={INPUT}
                type="email"
                required
                placeholder={t('auth.email')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
              {mode !== 'forgot' && (
                <div className="relative">
                  <input
                    className={`${INPUT} pr-10`}
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
              )}
              {unverified && (
                <p className="text-xs text-amber-200">
                  {t('auth.unverified')}{' '}
                  <button type="button" onClick={resend} disabled={busy || resent} className={LINK}>
                    {resent ? t('auth.resent') : t('auth.resend')}
                  </button>
                </p>
              )}
              {error && <p className="text-xs text-red-300">{error}</p>}
              <button type="submit" disabled={busy} className={PRIMARY}>
                {busy
                  ? '…'
                  : mode === 'login'
                    ? t('auth.signIn')
                    : mode === 'register'
                      ? t('auth.register')
                      : t('auth.sendReset')}
              </button>
            </form>

            <p className="mt-3 space-x-3 text-center text-xs text-slate-400">
              {mode === 'login' && (
                <>
                  <span>
                    {t('auth.noAccount')}{' '}
                    <button onClick={() => switchMode('register')} className={LINK}>
                      {t('auth.register')}
                    </button>
                  </span>
                  <button onClick={() => switchMode('forgot')} className={LINK}>
                    {t('auth.forgot')}
                  </button>
                </>
              )}
              {mode === 'register' && (
                <span>
                  {t('auth.haveAccount')}{' '}
                  <button onClick={() => switchMode('login')} className={LINK}>
                    {t('auth.signIn')}
                  </button>
                </span>
              )}
              {mode === 'forgot' && (
                <button onClick={() => switchMode('login')} className={LINK}>
                  {t('auth.backToLogin')}
                </button>
              )}
            </p>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
