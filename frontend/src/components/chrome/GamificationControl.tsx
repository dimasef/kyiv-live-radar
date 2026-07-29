import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import AuthModal from '@/components/auth/AuthModal'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useRadar } from '@/store'

import Switch from './Switch'

/** Settings toggle for the opt-in gamification layer. Off by default.
 *
 * Enabling has two gates, in order: (1) a session is required — cards live in
 * the account, so an anon user gets the auth modal first, and we continue once
 * they're in; (2) a safety confirmation — the whole point is coping during a
 * raid, never a reason to leave shelter. Disabling is immediate, no gates. */
export default function GamificationControl() {
  const { t } = useTranslation()
  const on = useRadar((s) => s.gamification)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const setGamification = useRadar((s) => s.setGamification)
  const [confirming, setConfirming] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)

  const change = (next: boolean) => {
    if (!next) {
      setGamification(false)
      return
    }
    if (!authed) {
      setAuthOpen(true) // need a session to store the collection
      return
    }
    setConfirming(true)
  }

  const closeAuth = () => {
    setAuthOpen(false)
    // Signed in during the modal → carry straight on to the safety prompt.
    if (useRadar.getState().authStatus === 'authed') setConfirming(true)
  }

  return (
    <div className="mt-2 rounded-xl border border-white/[0.05] bg-white/[0.02] p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={13} className="text-phosphor-soft/80" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {t('game.settingsTitle')}
          </span>
        </div>
        <Switch checked={on} onChange={change} label={t('game.settingsTitle')} />
      </div>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">{t('game.settingsHint')}</p>

      {authOpen && <AuthModal onClose={closeAuth} />}
      {confirming && (
        <ConfirmModal
          message={t('game.safetyConfirm')}
          confirmLabel={t('game.safetyConfirmYes')}
          cancelLabel={t('game.cancel')}
          tone="accent"
          onConfirm={() => setGamification(true)}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  )
}
