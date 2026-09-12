import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { MAP_PATH, navigate } from '@/router'

/** The shared frame of the two mailed-link landing pages: a centered card
 * with a title, a body, and — once the link has done its work — a way on. */
export default function EmailLinkPage({
  title,
  done,
  children,
}: {
  title: string
  done: boolean
  children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="flex h-full items-center justify-center bg-ink-950 px-4 text-slate-200">
      <div className="panel w-full max-w-sm space-y-4 p-5">
        <h1 className="font-display text-base font-bold text-slate-100">{title}</h1>
        {children}
        {done && (
          <button
            onClick={() => navigate(MAP_PATH)}
            className="w-full rounded-lg bg-phosphor px-3 py-2 text-sm font-semibold text-ink-950 transition-opacity hover:opacity-90"
          >
            {t('auth.toMap')}
          </button>
        )}
      </div>
    </div>
  )
}
