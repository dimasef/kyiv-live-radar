import { useState } from 'react'

import { type BugReport, type BugReportStatus } from '@/api'
import Overlay from '@/components/common/Overlay'
import { kyivStamp } from '@/lib/kyivTime'

const STATUS_LABEL: Record<BugReportStatus, string> = {
  new: 'Новий',
  in_progress: 'В роботі',
  closed: 'Закрито',
}

const STATUS_CLASS: Record<BugReportStatus, string> = {
  new: 'border-phosphor/30 bg-phosphor/10 text-phosphor-soft',
  in_progress: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
  closed: 'border-white/10 bg-white/[0.04] text-slate-500',
}

/** One ticket. The technical line is deliberately above the description: when
 * two reports describe "все зламалось", the version and device are what tell
 * them apart. */
export default function BugReportRow({
  report,
  onStatus,
  onDelete,
}: {
  report: BugReport
  onStatus: (status: BugReportStatus) => void
  onDelete: () => void
}) {
  const [zoomed, setZoomed] = useState(false)
  const ctx = report.context as Record<string, unknown>
  const viewport =
    ctx.viewport_w && ctx.viewport_h ? `${ctx.viewport_w}×${ctx.viewport_h}` : null
  const facts = [
    report.app_version && `v${report.app_version}`,
    report.browser,
    report.os,
    viewport,
    typeof ctx.dpr === 'number' ? `dpr ${ctx.dpr}` : null,
    // A page scale other than 1 is a finding in itself, so it is never hidden.
    typeof ctx.scale === 'number' && ctx.scale !== 1 ? `zoom ${ctx.scale}` : null,
    ctx.standalone ? 'PWA' : null,
    typeof ctx.route === 'string' && ctx.route !== '/' ? ctx.route : null,
  ].filter(Boolean)

  return (
    <li className="rounded-lg border border-white/[0.07] bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_CLASS[report.status]}`}
        >
          {STATUS_LABEL[report.status]}
        </span>
        <span className="font-mono text-[11px] text-slate-500">
          {kyivStamp(report.created_at)}
        </span>
        <span className="text-[11px] text-slate-400">
          {report.reporter?.display_name || report.reporter?.email || 'акаунт видалено'}
        </span>
      </div>

      <p className="mt-1.5 font-mono text-[11px] text-slate-500">{facts.join(' · ')}</p>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-200">
        {report.description}
      </p>

      {report.screenshot && (
        <button onClick={() => setZoomed(true)} className="mt-2 block">
          <img
            src={report.screenshot}
            alt=""
            className="max-h-40 rounded-lg border border-white/10 bg-black/40 object-contain"
          />
        </button>
      )}
      {zoomed && report.screenshot && (
        <Overlay onClose={() => setZoomed(false)} className="max-h-full max-w-full">
          <img src={report.screenshot} alt="" className="max-h-[80vh] rounded-lg" />
        </Overlay>
      )}

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {report.status !== 'in_progress' && (
          <button onClick={() => onStatus('in_progress')} className="btn text-[11px]">
            В роботу
          </button>
        )}
        {report.status !== 'closed' && (
          <button onClick={() => onStatus('closed')} className="btn text-[11px]">
            Закрити
          </button>
        )}
        {report.status !== 'new' && (
          <button onClick={() => onStatus('new')} className="btn text-[11px]">
            Повернути в нові
          </button>
        )}
        <button onClick={onDelete} className="btn btn--warn ml-auto text-[11px]">
          Видалити
        </button>
      </div>
    </li>
  )
}
