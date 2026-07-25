import { deleteEvent, setEventDistrict } from '@/api'
import { useRadar } from '@/store'
import type { ThreatEvent } from '@/types'

import AdminActionButton from './AdminActionButton'

/** One sighting under a track: reassign its district (fix a mislocation) or
 * delete it (remove a wrong sighting; deleting a track's last event cancels the
 * track). The store refreshes from the server's WS broadcast. */
export default function EventAdminRow({ event }: { event: ThreatEvent }) {
  const districts = useRadar((s) => s.districts)

  return (
    <li className="flex flex-wrap items-center gap-2 border-t border-white/[0.05] py-1.5 text-xs">
      <span className="min-w-0 flex-1 truncate text-slate-400" title={event.raw_text}>
        #{event.id} · {event.raw_text || '—'}
      </span>
      <select
        value={event.district_id}
        onChange={(e) => {
          void setEventDistrict(event.id, Number(e.target.value)).catch(() => {})
        }}
        className="rounded-md border border-white/15 bg-ink-900 px-1.5 py-1 text-xs text-slate-200"
      >
        {districts.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name_uk}
          </option>
        ))}
      </select>
      <AdminActionButton
        label="Видалити"
        tone="danger"
        confirm="Видалити цю подію з треку?"
        onRun={() => deleteEvent(event.id)}
      />
    </li>
  )
}
