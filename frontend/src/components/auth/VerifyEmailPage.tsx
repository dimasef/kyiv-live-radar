import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { tokenFromSearch } from '@/router'
import { useRadar } from '@/store'

import EmailLinkPage from './EmailLinkPage'

/** `/verify-email?token=…` from the registration mail. Verifies on a click,
 * never on load: mail scanners open links, and the token works once. */
export default function VerifyEmailPage() {
  const { t } = useTranslation()
  const verifyEmail = useRadar((s) => s.verifyEmail)
  const [token] = useState(tokenFromSearch)
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle')

  const confirm = async () => {
    if (!token) return
    setState('busy')
    try {
      await verifyEmail(token)
      setState('done')
    } catch {
      setState('error')
    }
  }

  return (
    <EmailLinkPage title={t('auth.verifyTitle')} done={state === 'done'}>
      {!token ? (
        <p className="text-sm text-red-300">{t('auth.noToken')}</p>
      ) : state === 'done' ? (
        <p className="text-sm text-slate-300">{t('auth.verified')}</p>
      ) : (
        <>
          <p className="text-sm text-slate-300">{t('auth.verifyHint')}</p>
          {state === 'error' && <p className="text-xs text-red-300">{t('auth.badToken')}</p>}
          <button
            onClick={confirm}
            disabled={state === 'busy'}
            className="w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {state === 'busy' ? '…' : t('auth.verifyButton')}
          </button>
        </>
      )}
    </EmailLinkPage>
  )
}
