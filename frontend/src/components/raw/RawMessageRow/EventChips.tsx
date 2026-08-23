import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { deleteNotice, fetchAdminThreat } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import TrackEditModal from '@/components/admin/TrackEditModal'
import type { RawMessage, Threat } from '@/types'

import { type NoticeSet } from '../NoticeControl'
import EventChip from './EventChip'
import type { ApplyTrack, DropEvent, MoveEvent } from './types'

/** The T/M code chips for the ThreatEvents this message produced, each tagged
 * with the target type its track carries. Wraps, so a "чисто" that closed a
 * dozen tracks lays out as rows instead of overflowing the card.
 *
 * Each chip opens the track it belongs to for editing. This is where a wrong
 * parse is actually SEEN — next to the text that caused it — and sending the
 * admin to hunt the same track down on the «Керування» tab was how bad parses
 * stayed on the map. */
export default function EventChips({
  item,
  onDropEvent,
  onMoveEvent,
  onApplyTrack,
  onSetNotice,
}: {
  item: RawMessage
  onDropEvent: DropEvent
  onMoveEvent: MoveEvent
  onApplyTrack: ApplyTrack
  onSetNotice: NoticeSet
}) {
  const { t } = useTranslation()
  // The track being edited, already loaded — the chip's click does the fetch, so
  // the dialog itself needs no effect to open (see TrackEditModal).
  const [editing, setEditing] = useState<Threat | null>(null)

  if (item.events.length === 0 && item.notice_id == null) return null
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {item.events.map((e) => (
        <EventChip
          key={e.event_id}
          event={e}
          onOpenTrack={() => fetchAdminThreat(e.threat_id).then(setEditing)}
          onDropped={() => onDropEvent(item.id, e.event_id)}
        />
      ))}
      {item.notice_id != null && (
        <span className="inline-flex items-center gap-1 rounded bg-sky-400/10 px-1.5 py-0.5 font-mono text-[10px] text-sky-300/80">
          N{item.notice_id}
          {item.notice_kind && (
            <span className="opacity-70">{t(`notice.${item.notice_kind}`)}</span>
          )}
          <AdminActionButton
            label="×"
            title="Прибрати нотіс зі стрічки"
            tone="danger"
            compact
            confirm={`Прибрати нотіс N${item.notice_id} зі стрічки?`}
            onRun={() => deleteNotice(item.notice_id!).then(() => onSetNotice(item.id, null))}
          />
        </span>
      )}
      {editing && (
        <TrackEditModal
          track={editing}
          onClose={() => setEditing(null)}
          onTrackChanged={onApplyTrack}
          onEventMoved={onMoveEvent}
          onEventDeleted={(eventId) => onDropEvent(item.id, eventId)}
        />
      )}
    </div>
  )
}
