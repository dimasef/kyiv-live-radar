import { useState } from 'react'

import { deleteEvent, regroupEvent, setEventDistrict, type Regroup } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import { kyivStamp } from '@/lib/kyivTime'
import { useRadar } from '@/store'
import type { Threat, ThreatEvent } from '@/types'

/** One sighting inside the track editor: where it landed, what it said, and the
 * four ways it can be wrong — wrong district, wrong track, its own track, or
 * not a sighting at all.
 *
 * The move target is a plain track id because that is how the operator reads
 * the evidence: every chip in «Весь фід» is labelled T{id}/M{id}, so the number
 * they need is already on screen next to the message that made them open this. */
export default function TrackEventRow({
  event,
  canSplit,
  onTracksChanged,
  onDeleted,
}: {
  event: ThreatEvent
  /** Splitting the only sighting of a track just renames the track — the source
   * empties and is dismissed, the split is identical. Offered only from 2 up. */
  canSplit: boolean
  onTracksChanged: (result: Regroup) => void
  onDeleted: (eventId: number, track: Threat) => void
}) {
  const districts = useRadar((s) => s.districts)
  const [moving, setMoving] = useState(false)
  const [target, setTarget] = useState('')

  const targetId = Number(target)
  const targetValid = target.trim() !== '' && Number.isInteger(targetId) && targetId > 0

  return (
    <li className="border-t border-white/[0.05] py-2">
      <div className="flex items-baseline gap-2 font-mono text-[10px] text-slate-500">
        <span>M{event.id}</span>
        <time className="tabular-nums">{kyivStamp(event.event_time)}</time>
        {event.source_name && <span className="truncate text-slate-400">{event.source_name}</span>}
        {event.event_target_type && (
          <span className="text-slate-500">{event.event_target_type}</span>
        )}
      </div>
      <p className="mt-1 break-words text-xs leading-snug text-slate-300">
        {event.raw_text || '—'}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <select
          value={event.district_id}
          onChange={(e) => {
            void setEventDistrict(event.id, Number(e.target.value)).catch(() => {})
          }}
          className="rounded-md border border-white/15 bg-ink-900 px-1.5 py-0.5 text-[11px] text-slate-200"
          aria-label={`Район події M${event.id}`}
        >
          {districts.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name_uk}
            </option>
          ))}
        </select>

        {moving ? (
          <>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value.replace(/\D/g, ''))}
              placeholder="T№"
              inputMode="numeric"
              autoFocus
              className="w-16 rounded-md border border-white/15 bg-ink-900 px-1.5 py-0.5 font-mono text-[11px] text-slate-200"
              aria-label="Номер треку, куди перенести"
            />
            {targetValid && (
              <AdminActionButton
                label="Перенести"
                tone="accent"
                compact
                onRun={() =>
                  regroupEvent(event.id, targetId).then((r) => {
                    setMoving(false)
                    setTarget('')
                    onTracksChanged(r)
                  })
                }
              />
            )}
            <button
              onClick={() => setMoving(false)}
              className="px-1 font-mono text-[10px] text-slate-500 hover:text-slate-300"
            >
              відміна
            </button>
          </>
        ) : (
          <button
            onClick={() => setMoving(true)}
            className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 hover:border-white/20 hover:text-slate-300"
          >
            → в трек
          </button>
        )}

        {canSplit && (
          <AdminActionButton
            label="Відокремити"
            title="Винести цю ціль в окремий трек"
            compact
            confirm={`Винести M${event.id} в окремий трек? Новий трек успадкує стан цього.`}
            onRun={() => regroupEvent(event.id, null).then(onTracksChanged)}
          />
        )}
        <AdminActionButton
          label="Видалити"
          tone="danger"
          compact
          confirm={`Видалити M${event.id}? Спостереження зникне зовсім — щоб лише перегрупувати його, скористайтесь «→ в трек».`}
          onRun={() => deleteEvent(event.id).then((t) => onDeleted(event.id, t))}
        />
      </div>
    </li>
  )
}
