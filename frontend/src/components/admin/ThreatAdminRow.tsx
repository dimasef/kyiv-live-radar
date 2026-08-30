import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { dismissThreat, setThreatType } from '@/api'
import type { TargetType, Threat } from '@/types'

import AdminActionButton from './AdminActionButton'
import { ADMIN_TARGET_TYPES } from './adminLayout'
import EventAdminRow from './EventAdminRow'

/** One active track: retype its target, cancel it (false positive), or expand
 * to edit its individual sightings. */
export default function ThreatAdminRow({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <li className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="font-mono">T{threat.id}</span>
        </button>
        <span className="text-xs text-slate-500">
          {threat.events.length} под. · {threat.target_count} ц.
        </span>
        <select
          value={threat.target_type}
          onChange={(e) => {
            void setThreatType(threat.id, e.target.value as TargetType).catch(() => {})
          }}
          className="ml-auto rounded-md border border-white/15 bg-ink-900 px-1.5 py-1 text-xs text-slate-200"
        >
          {ADMIN_TARGET_TYPES.map((tt) => (
            <option key={tt} value={tt}>
              {t(`target.${tt}`)}
            </option>
          ))}
        </select>
        <AdminActionButton
          label="Скасувати ціль"
          tone="danger"
          confirm="Скасувати цю ціль? Вона зникне з мапи та статистики."
          onRun={() => dismissThreat(threat.id)}
        />
      </div>

      {open && (
        <ul className="mt-1.5">
          {threat.events.map((ev) => (
            <EventAdminRow key={ev.id} event={ev} />
          ))}
          {threat.events.length === 0 && (
            <li className="py-1.5 text-xs text-slate-600">Без подій.</li>
          )}
        </ul>
      )}
    </li>
  )
}
