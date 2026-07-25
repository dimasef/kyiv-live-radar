import { RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  fetchDismissed,
  restoreAlert,
  restoreIncident,
  restoreThreat,
  type Dismissed,
} from '@/api'

import AdminActionButton from './AdminActionButton'

const EMPTY: Dismissed = { threats: [], incidents: [], alerts: [] }

/** Recently cancelled entities with a one-click restore — the undo surface for
 * an over-eager dismissal. Fetched on mount and re-fetched after each restore
 * (a restore both un-cancels the row and re-adds it to the live layer via WS). */
export default function DismissedList() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Dismissed>(EMPTY)

  const refresh = () => {
    fetchDismissed()
      .then(setItems)
      .catch(() => {})
  }
  useEffect(refresh, [])

  const restore = (run: () => Promise<unknown>) => async () => {
    await run()
    refresh()
  }

  const total = items.threats.length + items.incidents.length + items.alerts.length

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Нещодавно скасовані ({total})
      </h2>
      {total === 0 ? (
        <p className="text-xs text-slate-600">Порожньо.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.threats.map((th) => (
            <Row key={`t${th.id}`} label={`Ціль T${th.id} · ${t(`target.${th.target_type}`)}`}>
              <AdminActionButton
                label="Повернути"
                tone="accent"
                onRun={restore(() => restoreThreat(th.id))}
              />
            </Row>
          ))}
          {items.incidents.map((inc) => (
            <Row key={`i${inc.id}`} label={`Атака #${inc.id}`}>
              <AdminActionButton
                label="Повернути"
                tone="accent"
                onRun={restore(() => restoreIncident(inc.id))}
              />
            </Row>
          ))}
          {items.alerts.map((a) => (
            <Row key={`a${a.id}`} label={`Тривога #${a.id}`}>
              <AdminActionButton
                label="Повернути"
                tone="accent"
                onRun={restore(() => restoreAlert(a.id))}
              />
            </Row>
          ))}
        </ul>
      )}
      <button
        onClick={refresh}
        className="mt-2 flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
      >
        <RotateCcw size={12} /> Оновити
      </button>
    </section>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
      <span className="min-w-0 flex-1 truncate text-slate-300">{label}</span>
      {children}
    </li>
  )
}
