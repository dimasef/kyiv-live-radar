import { RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  fetchDismissed,
  restoreAlert,
  restoreIncident,
  restoreThreat,
  type Dismissed,
} from '@/api'

import { useAsyncData } from '@/lib/useAsyncData'

import AdminActionButton from './AdminActionButton'
import AdminLoading from './AdminLoading'
import AdminRegionList from './AdminRegionList'

const EMPTY: Dismissed = { threats: [], incidents: [], alerts: [] }

/** Recently cancelled entities with a one-click restore — the undo surface for
 * an over-eager dismissal. Fetched on mount and re-fetched after each restore
 * (a restore both un-cancels the row and re-adds it to the live layer via WS). */
export default function DismissedList() {
  const { t } = useTranslation()
  const { data: items, loaded, reload } = useAsyncData<Dismissed>(fetchDismissed, [], EMPTY)

  const restore = (run: () => Promise<unknown>) => async () => {
    await run()
    reload()
  }

  const total = items.threats.length + items.incidents.length + items.alerts.length
  // One list across the three kinds, so a region block holds everything that
  // was cancelled over that oblast rather than three separate piles.
  const rows = [
    ...items.threats.map((th) => ({
      key: `t${th.id}`, region: th.region,
      label: `Ціль T${th.id} · ${t(`target.${th.target_type}`)}`,
      run: () => restoreThreat(th.id),
    })),
    ...items.incidents.map((inc) => ({
      key: `i${inc.id}`, region: inc.region, label: `Атака #${inc.id}`,
      run: () => restoreIncident(inc.id),
    })),
    ...items.alerts.map((a) => ({
      key: `a${a.id}`, region: a.region, label: `Тривога #${a.id}`,
      run: () => restoreAlert(a.id),
    })),
  ]

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Нещодавно скасовані ({total})
      </h2>
      {!loaded ? (
        <AdminLoading rows={2} />
      ) : total === 0 ? (
        <p className="text-xs text-slate-600">Порожньо.</p>
      ) : (
        <AdminRegionList items={rows} regionOf={(r) => r.region}>
          {(row) => (
            <Row key={row.key} label={row.label}>
              <AdminActionButton
                label="Повернути"
                tone="accent"
                onRun={restore(row.run)}
              />
            </Row>
          )}
        </AdminRegionList>
      )}
      <button
        onClick={reload}
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
