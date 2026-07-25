import { dismissAlert } from '@/api'
import { useRadar } from '@/store'

import AdminActionButton from './AdminActionButton'

/** Open official air-raid alerts (banner source). Cancelling clears a
 * city/oblast alert that was raised in error. */
export default function ActiveAlertList() {
  const alerts = useRadar((s) => s.alerts)
  const open = alerts.filter((a) => !a.ended_at)

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Активні тривоги ({open.length})
      </h2>
      {open.length === 0 ? (
        <p className="text-xs text-slate-600">Немає активних тривог.</p>
      ) : (
        <ul className="space-y-1.5">
          {open.map((alert) => (
            <li
              key={alert.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs"
            >
              <span className="font-mono text-slate-300">Тривога #{alert.id}</span>
              <span className="text-slate-500">{alert.scope === 'city' ? 'місто' : 'область'}</span>
              <div className="ml-auto">
                <AdminActionButton
                  label="Скасувати тривогу"
                  tone="danger"
                  confirm="Скасувати цю тривогу?"
                  onRun={() => dismissAlert(alert.id)}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
