import { Bug, Check } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError, submitBugReport } from '@/api'
import { AuthModal } from '@/components/auth'
import Overlay from '@/components/common/Overlay'
import { collectClientContext } from '@/lib/clientContext'
import { imageFromClipboard, ScreenshotError, toScreenshotDataUrl } from '@/lib/screenshotImage'
import { useRadar } from '@/store'

import ContextSummary from './ContextSummary'
import ScreenshotField from './ScreenshotField'

/** The report form. Mounted once in the app shell; opened from the settings
 * drawer and the account menu (store: `bugReportOpen`).
 *
 * The context is collected when the form OPENS, not when it is submitted: by
 * the time someone finishes typing they may have rotated the phone or closed a
 * keyboard, and the numbers that matter are the ones from when the bug was in
 * front of them. */
export default function BugReportModal() {
  const { t } = useTranslation()
  const authed = useRadar((s) => s.authStatus === 'authed')
  const close = useRadar((s) => s.setBugReportOpen)
  const [context] = useState(collectClientContext)
  const [description, setDescription] = useState('')
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)

  const dismiss = () => close(false)

  const acceptFile = async (file: File) => {
    setError(null)
    try {
      setScreenshot(await toScreenshotDataUrl(file))
    } catch (e) {
      setError(e instanceof ScreenshotError ? e.message : t('bug.imageFailed'))
    }
  }

  // Either half is enough to act on; an empty form is not. The button says so
  // by being disabled, so nobody types into a void and then reads an error.
  const canSend = description.trim().length > 0 || screenshot !== null

  const submit = async () => {
    setSending(true)
    setError(null)
    try {
      await submitBugReport(description.trim(), screenshot, context)
      setSent(true)
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 429 ? t('bug.rateLimited') : t('bug.failed'),
      )
    } finally {
      setSending(false)
    }
  }

  if (loginOpen) return <AuthModal onClose={() => setLoginOpen(false)} />

  return (
    <Overlay
      onClose={dismiss}
      className="rise w-full max-w-md rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl"
    >
      <h2 className="flex items-center gap-2 font-display text-base font-bold text-slate-100">
        <Bug size={16} className="text-phosphor-soft" />
        {t('bug.title')}
      </h2>

      {sent ? (
        <>
          <p className="mt-3 flex items-center gap-2 text-sm text-slate-300">
            <Check size={16} className="flex-none text-emerald-400" />
            {t('bug.sent')}
          </p>
          <button onClick={dismiss} className="btn btn--accent mt-4 w-full">
            {t('bug.close')}
          </button>
        </>
      ) : !authed ? (
        <>
          <p className="mt-3 text-sm text-slate-400">{t('bug.needAuth')}</p>
          <button onClick={() => setLoginOpen(true)} className="btn btn--accent mt-4 w-full">
            {t('bug.signIn')}
          </button>
        </>
      ) : (
        <>
          <p className="mt-1 text-xs text-slate-500">{t('bug.intro')}</p>
          <textarea
            autoFocus
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onPaste={(e) => {
              // A pasted screenshot belongs in the attachment, not as garbage
              // text in the description.
              const file = imageFromClipboard(e.clipboardData)
              if (!file) return
              e.preventDefault()
              void acceptFile(file)
            }}
            placeholder={t('bug.placeholder')}
            className="mt-3 w-full resize-none rounded-lg border border-white/10 bg-black/30 p-2.5 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-phosphor/40"
          />

          <ScreenshotField
            value={screenshot}
            onFile={(file) => void acceptFile(file)}
            onClear={() => setScreenshot(null)}
          />
          <ContextSummary context={context} />

          {error && <p className="mt-2 text-xs text-orange-400">{error}</p>}

          <div className="mt-4 flex gap-2">
            <button onClick={dismiss} className="btn flex-1">
              {t('bug.cancel')}
            </button>
            <button
              onClick={() => void submit()}
              disabled={sending || !canSend}
              title={canSend ? undefined : t('bug.needSomething')}
              className="btn btn--accent flex-1 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sending ? t('bug.sending') : t('bug.send')}
            </button>
          </div>
        </>
      )}
    </Overlay>
  )
}
