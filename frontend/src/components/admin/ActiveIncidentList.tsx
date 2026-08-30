import { useTranslation } from 'react-i18next'

import { dismissIncident } from '@/api'
import { useRadar } from '@/store'

import AdminActionButton from './AdminActionButton'
import AdminRegionList from './AdminRegionList'

/** Ongoing attacks (incident rollups). Cancelling an attack also cancels all of
 * its member tracks in one action — for when a whole raid was raised in error. */
export default function ActiveIncidentList() {
  const { t } = useTranslation()
  const incidents = useRadar((s) => s.incidents)

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Активні атаки ({incidents.length})
      </h2>
      {incidents.length === 0 ? (
        <p className="text-xs text-slate-600">Немає активних атак.</p>
      ) : (
        <AdminRegionList items={incidents} regionOf={(i) => i.region}>
          {(inc) => (
            <li
              key={inc.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs"
            >
              <span className="font-mono text-slate-300">Атака #{inc.id}</span>
              <span className="text-slate-500">
                {t(`target.${inc.target_type}`)} · {inc.track_count} тр.
              </span>
              <div className="ml-auto">
                <AdminActionButton
                  label="Скасувати атаку"
                  tone="danger"
                  confirm="Скасувати всю атаку разом з усіма її цілями?"
                  onRun={() => dismissIncident(inc.id)}
                />
              </div>
            </li>
          )}
        </AdminRegionList>
      )}
    </section>
  )
}
