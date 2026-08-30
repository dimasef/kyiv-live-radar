import { useCallback, useState } from 'react'

import {
  deleteBugReport,
  fetchBugReports,
  setBugReportStatus,
  type BugReport,
  type BugReportStatus,
} from '@/api'

import { useAsyncData } from '@/lib/useAsyncData'

import { ADMIN_WIDTH } from './adminLayout'
import BugReportRow from './BugReportRow'

const FILTERS: { key: BugReportStatus | 'all'; label: string }[] = [
  { key: 'new', label: 'Нові' },
  { key: 'in_progress', label: 'В роботі' },
  { key: 'closed', label: 'Закриті' },
  { key: 'all', label: 'Усі' },
]

/** What users reported from inside the app, newest first. Read-mostly, so a
 * fetch per filter change is the simplest correct sync (same as the other
 * admin panels). */
export default function BugReportsPanel() {
  const [filter, setFilter] = useState<BugReportStatus | 'all'>('new')
  const {
    data: reports,
    loaded,
    setData: setReports,
  } = useAsyncData<BugReport[]>(
    useCallback(() => fetchBugReports(filter === 'all' ? undefined : filter), [filter]),
    [filter],
    [],
  )

  const applyStatus = async (report: BugReport, status: BugReportStatus) => {
    const updated = await setBugReportStatus(report.id, status)
    setReports((rs) =>
      // A ticket that no longer matches the open filter leaves the list.
      filter !== 'all' && updated.status !== filter
        ? rs.filter((r) => r.id !== report.id)
        : rs.map((r) => (r.id === report.id ? updated : r)),
    )
  }

  const remove = async (report: BugReport) => {
    await deleteBugReport(report.id)
    setReports((rs) => rs.filter((r) => r.id !== report.id))
  }

  return (
    <div className={`${ADMIN_WIDTH} flex flex-col gap-3 px-4 py-4`}>
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${
              filter === f.key
                ? 'border-phosphor/40 bg-phosphor/10 text-phosphor-soft'
                : 'border-white/10 text-slate-400 hover:text-slate-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loaded && reports.length === 0 && <p className="text-xs text-slate-600">Порожньо.</p>}

      <ul className="space-y-2">
        {reports.map((report) => (
          <BugReportRow
            key={report.id}
            report={report}
            onStatus={(status) => void applyStatus(report, status).catch(() => {})}
            onDelete={() => void remove(report).catch(() => {})}
          />
        ))}
      </ul>
    </div>
  )
}
