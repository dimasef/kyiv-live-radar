import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { addRawNotice } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import type { NoticeKind, RawMessage } from '@/types'

/** Kind -> translation key, or null for a kind that must not be published by
 * hand. A Record (not an array) so a new backend notice kind fails to compile
 * here instead of quietly missing from the picker. Ordered by how often it's the
 * right answer by hand: a forecast is the classic thing the suppression filters
 * drop and an operator wants published anyway. */
const KIND_LABEL: Record<NoticeKind, string | null> = {
  forecast: 'notice.forecast',
  status: 'notice.status',
  summary: 'notice.summary',
  clear: 'notice.clear',
  directional: 'notice.directional',
  // Raised only by an alert whose level actually moved (backend
  // pipeline/ingest/alert.py). Published by hand it would announce an
  // escalation of an alert that never changed.
  alert_level: null,
}
const KINDS = (Object.entries(KIND_LABEL) as [NoticeKind, string | null][])
  .filter((entry): entry is [NoticeKind, string] => entry[1] !== null)

export type NoticeSet = (messageId: number, notice: { id: number; kind: string } | null) => void

/** Publish this message to the event feed by hand, as a notice of a chosen kind.
 *
 * Collapsed to a single "+ нотіс" until asked for: this sits on every row of a
 * list scrolled in the hundreds, and a permanent picker per row would bury the
 * messages themselves. Renders nothing once the message already has a notice —
 * the row's own N chip takes over from there. */
export default function NoticeControl({
  item,
  onSetNotice,
}: {
  item: RawMessage
  onSetNotice: NoticeSet
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<NoticeKind>('forecast')

  if (item.notice_id != null) return null

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-1.5 rounded border border-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 hover:border-white/20 hover:text-slate-300"
      >
        + нотіс
      </button>
    )
  }

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      <select
        value={kind}
        onChange={(e) => setKind(e.target.value as NoticeKind)}
        className="rounded-md border border-white/15 bg-ink-900 px-1.5 py-0.5 text-[11px] text-slate-200"
        aria-label="Тип нотіса"
      >
        {KINDS.map(([k, labelKey]) => (
          <option key={k} value={k}>
            {t(labelKey)}
          </option>
        ))}
      </select>
      <AdminActionButton
        label="У стрічку"
        tone="accent"
        compact
        onRun={() =>
          addRawNotice(item.id, kind).then((n) => {
            setOpen(false)
            onSetNotice(item.id, { id: n.id, kind: n.kind })
          })
        }
      />
      <button
        onClick={() => setOpen(false)}
        className="px-1 font-mono text-[10px] text-slate-500 hover:text-slate-300"
      >
        відміна
      </button>
    </div>
  )
}
