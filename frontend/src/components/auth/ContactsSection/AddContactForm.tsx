import { UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api'
import { useRadar } from '@/store'

export default function AddContactForm() {
  const { t } = useTranslation()
  const requestFriend = useRadar((s) => s.requestFriend)

  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const value = email.trim()
    if (!value || busy) return
    setBusy(true)
    setMsg(null)
    try {
      const { status } = await requestFriend(value)
      setEmail('')
      setMsg({ tone: 'ok', text: t(`friends.result.${status}`) })
    } catch (e) {
      const key = e instanceof ApiError && e.status === 404 ? 'notFound' : 'failed'
      setMsg({ tone: 'err', text: t(`friends.error.${key}`) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
          placeholder={t('friends.emailPlaceholder')}
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-slate-200 placeholder:text-slate-600 focus:border-phosphor/40 focus:outline-none"
        />
        <button
          onClick={() => void submit()}
          disabled={busy || !email.trim()}
          className="btn btn--accent flex items-center gap-1.5 disabled:opacity-40"
        >
          <UserPlus size={14} />
          {t('friends.add')}
        </button>
      </div>
      {msg && (
        <p className={`mt-1.5 text-xs ${msg.tone === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}
