import { ArrowRight, Crosshair, Split, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { deleteEvent, regroupEvent, setEventDistrict, type Regroup } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import ConfirmModal from '@/components/common/ConfirmModal'
import { kyivStamp } from '@/lib/kyivTime'
import { useRadar } from '@/store'
import type { Threat, ThreatEvent } from '@/types'

/** Thumb-sized, because this editor's real home is a phone held one-handed
 * during a raid. Every control in the row shares the height so the row reads as
 * one band instead of a ransom note. */
const TAP =
  'inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-white/10 ' +
  'bg-white/[0.03] px-2.5 text-[11px] text-slate-400 transition-colors ' +
  'hover:border-white/20 hover:text-slate-200 active:bg-white/[0.07]'

/** One sighting inside the track editor: what it said, where it landed, and the
 * four ways it can be wrong — wrong district, wrong track, its own track, or
 * not a sighting at all.
 *
 * The message text leads, at reading size, because it is the evidence the
 * operator is here to judge; the controls follow in ONE row underneath. It used
 * to be the other way round — a full-width district select on top and four
 * 18px buttons wrapping onto three lines — which made three sightings fill a
 * phone screen and put «Видалити» under every thumb.
 *
 * The move target is a plain track id because that is how the operator reads
 * the evidence: every chip in «Весь фід» is labelled T{id}/M{id}, so the number
 * they need is already on screen next to the message that made them open this.
 * On the map there is no such number, which is what `onPickOnMap` is for. */
export default function TrackEventRow({
  event,
  canSplit,
  onTracksChanged,
  onDeleted,
  onPickOnMap,
}: {
  event: ThreatEvent
  /** Splitting the only sighting of a track just renames the track — the source
   * empties and is dismissed, the split is identical. Offered only from 2 up. */
  canSplit: boolean
  onTracksChanged: (result: Regroup) => void
  onDeleted: (eventId: number, track: Threat) => void
  /** Given only by the on-map editor: pick the destination track by clicking it
   * on the map instead of typing its number. */
  onPickOnMap?: () => void
}) {
  const { t } = useTranslation()
  const districts = useRadar((s) => s.districts)
  const [moving, setMoving] = useState(false)
  const [target, setTarget] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // The icon button can't fall back to AdminActionButton's inline «Помилка»
  // label, and a delete that silently did nothing is the worst of both.
  const [deleteFailed, setDeleteFailed] = useState(false)

  const targetId = Number(target)
  const targetValid = target.trim() !== '' && Number.isInteger(targetId) && targetId > 0

  const remove = async () => {
    setDeleting(true)
    setDeleteFailed(false)
    try {
      onDeleted(event.id, await deleteEvent(event.id))
    } catch {
      setDeleteFailed(true)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <li className="border-t border-white/[0.06] py-3">
      <div className="flex items-baseline gap-2 font-mono text-[10px] text-slate-500">
        <span className="flex-none">M{event.id}</span>
        <time className="flex-none tabular-nums">{kyivStamp(event.event_time)}</time>
        {/* A chip, not loose text: a track that needs editing is usually one
            that mixes channels, and the channel is what the operator scans by.
            Same shape as the T/M chips in «Весь фід» (raw/EventChip). */}
        {event.source_name && (
          <span
            title={event.source_name}
            className="inline-block max-w-[9rem] truncate rounded bg-white/[0.04] px-1.5 py-0.5 text-slate-300"
          >
            {event.source_name}
          </span>
        )}
        {event.event_target_type && (
          <span className="ml-auto flex-none text-slate-400">
            {t(`target.${event.event_target_type}`)}
          </span>
        )}
      </div>

      <p className="mt-1 break-words text-[13px] leading-snug text-slate-200">
        {event.raw_text || '—'}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {/* The widest control of the row but not a full-width one: the district
            is right far more often than it is wrong, so it states the current
            answer rather than demanding a new one. */}
        <select
          value={event.district_id}
          onChange={(e) => {
            void setEventDistrict(event.id, Number(e.target.value)).catch(() => {})
          }}
          className="h-9 min-w-0 max-w-[11rem] flex-1 rounded-lg border border-white/10 bg-ink-900 px-2 text-[11px] text-slate-300"
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
              className="h-9 w-16 rounded-lg border border-phosphor/40 bg-ink-900 px-2 font-mono text-xs text-slate-100"
              aria-label="Номер треку, куди перенести"
            />
            {targetValid && (
              <AdminActionButton
                label="Перенести"
                tone="accent"
                onRun={() =>
                  regroupEvent(event.id, targetId).then((r) => {
                    setMoving(false)
                    setTarget('')
                    onTracksChanged(r)
                  })
                }
              />
            )}
            <button onClick={() => setMoving(false)} className={TAP}>
              відміна
            </button>
          </>
        ) : (
          <>
            <button onClick={() => setMoving(true)} className={TAP} title="Перенести в інший трек">
              <ArrowRight size={13} className="flex-none" />
              трек
            </button>
            {onPickOnMap && (
              <button onClick={onPickOnMap} className={TAP} title="Обрати ціль кліком по мапі">
                <Crosshair size={13} className="flex-none" />
                мапа
              </button>
            )}
            {canSplit && (
              <AdminActionButton
                label="окремо"
                icon={<Split size={13} className="flex-none" />}
                title="Винести цю ціль в окремий трек"
                confirm={`Винести M${event.id} в окремий трек? Новий трек успадкує стан цього.`}
                onRun={() => regroupEvent(event.id, null).then(onTracksChanged)}
              />
            )}
          </>
        )}

        {/* Pushed to the far edge and reduced to its glyph. It is the only
            action here that destroys a real observation, and it should never be
            the neighbour of the one the thumb was actually aiming for. */}
        <button
          onClick={() => setConfirmingDelete(true)}
          disabled={deleting}
          title={deleteFailed ? 'Не вдалося видалити — спробуйте ще раз' : 'Видалити спостереження'}
          aria-label={`Видалити M${event.id}`}
          className={`ml-auto inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg transition-colors hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-40 ${
            deleteFailed ? 'bg-rose-500/10 text-rose-300' : 'text-slate-600'
          }`}
        >
          <Trash2 size={14} />
        </button>
      </div>

      {confirmingDelete && (
        <ConfirmModal
          message={`Видалити M${event.id}? Спостереження зникне зовсім — щоб лише перегрупувати його, скористайтесь «трек» або «мапа».`}
          confirmLabel="Видалити"
          tone="danger"
          onConfirm={remove}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </li>
  )
}
