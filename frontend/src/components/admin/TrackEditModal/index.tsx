import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { dismissThreat, restoreThreat, setThreatType, type Regroup } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import { useDismissTransition } from '@/lib/useDismissTransition'
import type { TargetType, Threat } from '@/types'

import TrackEventRow from './TrackEventRow'

const TARGET_TYPES: TargetType[] = [
  'shahed', 'jet_drone', 'fpv', 'missile', 'ballistic', 'unknown',
]

/** Edit one track without leaving «Весь фід»: its type, its lifecycle, and the
 * grouping of the sightings under it.
 *
 * Grouping is the reason this exists. Tracking joins sightings by reply-chain
 * and same-district corroboration, and when it is wrong the result is either
 * one target split across tracks or two targets merged into one — and the only
 * repair used to be DELETING a sighting, which throws away a real observation
 * to fix a bookkeeping mistake. Here the same sighting can be moved instead.
 *
 * No fetch-on-mount: the opener loads the track and every action below answers
 * with the track's new state, so the dialog never has to re-ask the server. */
export default function TrackEditModal({
  track: initial,
  onClose,
  onTrackChanged,
  onEventMoved,
  onEventDeleted,
}: {
  track: Threat
  onClose: () => void
  /** A track's server state changed — the list folds it into every chip of it. */
  onTrackChanged: (track: Threat) => void
  onEventMoved: (eventId: number, threatId: number) => void
  onEventDeleted: (eventId: number) => void
}) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)
  const [track, setTrack] = useState(initial)

  const applyTrack = (next: Threat) => {
    setTrack(next)
    onTrackChanged(next)
  }

  /** A regroup always answers with BOTH tracks. The one this dialog is showing
   * is whichever of them still owns these sightings — after a split that is the
   * source; after a move onto another track it is the source too, minus the
   * sighting that left. */
  const applyRegroup = (r: Regroup) => {
    // Re-point the chip FIRST, then fold in both tracks' state: the two are
    // sequential updates of the same list, and folding first would leave the
    // moved chip matching neither track — new id, stale type and fusion.
    onEventMoved(r.event_id, r.threat.id)
    onTrackChanged(r.threat)
    onTrackChanged(r.source_threat)
    setTrack(r.source_threat.id === track.id ? r.source_threat : r.threat)
  }

  const open = track.closed_at == null

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        className={`flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border border-white/10 bg-ink-900 shadow-2xl transition-all duration-200 ease-out ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shrink-0 border-b border-white/[0.06] px-5 pt-4 pb-3">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-display text-sm font-bold text-slate-100">
              Трек <span className="font-mono">T{track.id}</span>
            </h2>
            <button
              onClick={close}
              className="rounded px-1.5 text-slate-500 hover:text-slate-200"
              aria-label="Закрити"
            >
              ×
            </button>
          </div>
          <p className="mt-1 font-mono text-[10px] text-slate-500">
            {track.events.length} под. · {track.target_count} ц. ·{' '}
            {track.corroboration_count} дж. · {Math.round(track.confidence * 100)}%
            {track.incident_id != null && <> · I{track.incident_id}</>}
            {track.closed_reason && <> · {track.closed_reason}</>}
          </p>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <select
              value={track.target_type}
              onChange={(e) => {
                void setThreatType(track.id, e.target.value as TargetType)
                  .then(applyTrack)
                  .catch(() => {})
              }}
              className="rounded-md border border-white/15 bg-ink-900 px-1.5 py-1 text-xs text-slate-200"
              aria-label="Тип цілі треку"
            >
              {TARGET_TYPES.map((tt) => (
                <option key={tt} value={tt}>
                  {t(`target.${tt}`)}
                </option>
              ))}
            </select>
            {open ? (
              <AdminActionButton
                label="Скасувати ціль"
                tone="danger"
                confirm="Скасувати цю ціль? Вона зникне з мапи та статистики."
                onRun={() => dismissThreat(track.id).then(applyTrack)}
              />
            ) : (
              <AdminActionButton
                label="Повернути ціль"
                onRun={() => restoreThreat(track.id).then(applyTrack)}
              />
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-1">
          <ul>
            {track.events.map((ev) => (
              <TrackEventRow
                key={ev.id}
                event={ev}
                canSplit={track.events.length > 1}
                onTracksChanged={applyRegroup}
                onDeleted={(eventId, updated) => {
                  onEventDeleted(eventId)
                  applyTrack(updated)
                }}
              />
            ))}
          </ul>
          {track.events.length === 0 && (
            <p className="py-4 text-center text-xs text-slate-600">
              Без подій — трек більше нічого не описує.
            </p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
