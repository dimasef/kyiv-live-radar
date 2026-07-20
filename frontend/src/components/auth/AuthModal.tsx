import { X } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { createPortal } from 'react-dom'

import { ApiError } from '@/api'
import { useRadar } from '@/store'

import GoogleButton from './GoogleButton'
import TelegramButton from './TelegramButton'

type Mode = 'login' | 'register'

const HAS_SSO = Boolean(
  import.meta.env.VITE_GOOGLE_CLIENT_ID || import.meta.env.VITE_TELEGRAM_LOGIN_BOT,
)

function errorMessage(err: unknown, mode: Mode): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Невірна пошта або пароль'
    if (err.status === 400) return 'Ця пошта вже зареєстрована'
    if (err.status === 422) return 'Пароль має містити щонайменше 8 символів'
    if (err.status === 503) return 'Вхід тимчасово недоступний'
  }
  return mode === 'login' ? 'Не вдалося увійти' : 'Не вдалося зареєструватися'
}

/** Email/password sign-in + registration, with the SSO buttons when any
 * provider is configured. Closes itself on success. */
export default function AuthModal({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const login = useRadar((s) => s.login)
  const register = useRadar((s) => s.register)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'login') await login(email.trim().toLowerCase(), password)
      else await register(email.trim().toLowerCase(), password, name.trim() || undefined)
      onClose()
    } catch (err) {
      setError(errorMessage(err, mode))
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
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-base font-bold text-slate-100">
            {mode === 'login' ? 'Вхід' : 'Реєстрація'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200" aria-label="Закрити">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-2.5">
          {mode === 'register' && (
            <input
              className={input}
              placeholder="Ім'я (необов'язково)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          )}
          <input
            className={input}
            type="email"
            required
            placeholder="Пошта"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <input
            className={input}
            type="password"
            required
            minLength={mode === 'register' ? 8 : undefined}
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
          {error && <p className="text-xs text-red-300">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? '…' : mode === 'login' ? 'Увійти' : 'Зареєструватися'}
          </button>
        </form>

        <button
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
          className="mt-3 w-full text-center text-xs text-slate-400 hover:text-phosphor-soft"
        >
          {mode === 'login' ? 'Немає акаунта? Зареєструватися' : 'Уже маєте акаунт? Увійти'}
        </button>

        {HAS_SSO && (
          <>
            <div className="my-4 flex items-center gap-3 text-[11px] text-slate-600">
              <span className="h-px flex-1 bg-white/10" />
              або
              <span className="h-px flex-1 bg-white/10" />
            </div>
            <div className="space-y-2">
              <GoogleButton onError={() => setError('Не вдалося увійти через Google')} />
              <TelegramButton onError={() => setError('Не вдалося увійти через Telegram')} />
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
