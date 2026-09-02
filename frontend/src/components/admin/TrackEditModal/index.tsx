import { useState } from 'react'
import { createPortal } from 'react-dom'

import { type Regroup } from '@/api'
import { useDismissTransition } from '@/lib/useDismissTransition'
import type { Threat, ThreatEvent } from '@/types'

import TrackEventRow from './TrackEventRow'
import TrackHeader from './TrackHeader'

/** Edit one track without leaving the surface it was spotted on: its type, its
 * group size, its lifecycle, and the grouping of the sightings under it.
 *
 * Grouping is the reason this exists. Tracking joins sightings by reply-chain
 * and same-district corroboration, and when it is wrong the result is either
 * one target split across tracks or two targets merged into one — and the only
 * repair used to be DELETING a sighting, which throws away a real observation
 * to fix a bookkeeping mistake. Here the same sighting can be moved instead.
 *
 * A bottom sheet on a phone and a centered dialog on a desktop — one element
 * with responsive classes, not two shells: a long track is a scrolling list,
 * and a list is worked from the bottom of the screen where the thumb already
 * is.
 *
 * No fetch-on-mount: the opener loads the track and every action below answers
 * with the track's new state, so the dialog never has to re-ask the server. */
export default function TrackEditModal({
  track: initial,
  onClose,
  onTrackChanged,
  onEventMoved,
  onEventDeleted,
  onPickOnMap,
}: {
  track: Threat
  onClose: () => void
  /** A track's server state changed — the list folds it into every chip of it. */
  onTrackChanged: (track: Threat) => void
  onEventMoved: (eventId: number, threatId: number) => void
  onEventDeleted: (eventId: number) => void
  /** Offered only where there IS a map to pick on (the on-map editor): hand the
   * sighting to the caller, which puts the map into pick mode. Absent in «Весь
   * фід», where a track is named by the T-number already on screen. */
  onPickOnMap?: (event: ThreatEvent) => void
}) {
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

  // Newest first. `Threat.events` arrives oldest-first (the server orders by
  // event_time, and the map draws the trajectory in that order), but this list
  // is not a trajectory — it is a work queue, and on a track with a long
  // history the sighting most likely to need fixing is the one that just
  // landed. Oldest-first put it below the fold every time.
  const newestFirst = [...track.events].reverse()

  const body = (
    <>
      <TrackHeader track={track} onClose={close} onChanged={applyTrack} />
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-1 sm:px-5">
        <ul>
          {newestFirst.map((ev) => (
            <TrackEventRow
              key={ev.id}
              event={ev}
              canSplit={track.events.length > 1}
              onTracksChanged={applyRegroup}
              onPickOnMap={onPickOnMap && (() => onPickOnMap(ev))}
              onDeleted={(eventId, updated) => {
                onEventDeleted(eventId)
                applyTrack(updated)
              }}
            />
          ))}
        </ul>
        {track.events.length === 0 && (
          <p className="py-6 text-center text-xs text-slate-600">
            Без подій — трек більше нічого не описує.
          </p>
        )}
      </div>
    </>
  )

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex flex-col justify-end bg-ink-950/80 backdrop-blur-sm transition-opacity duration-200 sm:items-center sm:justify-center sm:p-4 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      {/* One tree, two shells. Rendering the body twice behind `sm:hidden` /
          `hidden sm:flex` would mount every sighting row twice — duplicate
          state and duplicate aria-labels for a list that can run long. */}
      <div
        onClick={(e) => e.stopPropagation()}
        className={`flex max-h-[88vh] w-full flex-col rounded-t-2xl border-t border-white/10 bg-ink-900 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-2xl transition-all duration-300 ease-out sm:max-h-[85vh] sm:max-w-lg sm:rounded-2xl sm:border sm:pb-0 sm:duration-200 ${
          shown
            ? 'translate-y-0 sm:scale-100 sm:opacity-100'
            : 'translate-y-full sm:translate-y-2 sm:scale-95 sm:opacity-0'
        }`}
      >
        {/* Grab handle — the phone sheet's affordance, meaningless on desktop. */}
        <div className="mx-auto mt-2 mb-1 h-1 w-9 flex-none rounded-full bg-white/15 sm:hidden" />
        {body}
      </div>
    </div>,
    document.body,
  )
}
