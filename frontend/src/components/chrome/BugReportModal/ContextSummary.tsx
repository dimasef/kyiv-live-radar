import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { BugContext } from '@/api'

/** What rides along with the report, shown to the person sending it.
 * Collapsed, but never hidden: this is data about their device, and they get to
 * read it before it's sent. */
export default function ContextSummary({ context }: { context: BugContext }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const rows: [string, string][] = [
    [t('bug.ctxVersion'), `v${context.app_version ?? '—'}`],
    [t('bug.ctxScreen'), `${context.viewport_w}×${context.viewport_h} @${context.dpr}×`],
    [t('bug.ctxPage'), context.route || '/'],
    [t('bug.ctxSystem'), context.user_agent ?? '—'],
  ]

  return (
    <div className="mt-3 rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left text-[11px] text-slate-500 hover:text-slate-300"
      >
        {t('bug.context')}
        <span className="font-mono">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <dl className="mt-2 space-y-1">
          {rows.map(([label, value]) => (
            <div key={label} className="flex gap-2 text-[11px]">
              <dt className="w-20 flex-none text-slate-600">{label}</dt>
              <dd className="min-w-0 break-words font-mono text-slate-400">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
