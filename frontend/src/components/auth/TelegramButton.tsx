import { useEffect, useRef } from 'react'

import type { TelegramAuthPayload } from '@/api'
import { useRadar } from '@/store'

const BOT = import.meta.env.VITE_TELEGRAM_LOGIN_BOT

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramAuthPayload) => void
  }
}

/** Telegram Login Widget. Dormant unless VITE_TELEGRAM_LOGIN_BOT (the bot's
 * username) is set. The widget injects an iframe and invokes a global callback;
 * we forward its payload verbatim so the backend can re-verify the HMAC. */
export default function TelegramButton({ onError }: { onError?: (e: unknown) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const loginWithTelegram = useRadar((s) => s.loginWithTelegram)

  useEffect(() => {
    const container = ref.current
    if (!BOT || !container) return
    window.onTelegramAuth = (user) =>
      loginWithTelegram(user).catch((e: unknown) => onError?.(e))
    const s = document.createElement('script')
    s.src = 'https://telegram.org/js/telegram-widget.js?22'
    s.async = true
    s.setAttribute('data-telegram-login', BOT)
    s.setAttribute('data-size', 'large')
    s.setAttribute('data-radius', '10')
    s.setAttribute('data-onauth', 'onTelegramAuth(user)')
    s.setAttribute('data-request-access', 'write')
    container.appendChild(s)
    return () => {
      container.innerHTML = ''
    }
  }, [loginWithTelegram, onError])

  if (!BOT) return null
  return <div ref={ref} className="flex justify-center" />
}
