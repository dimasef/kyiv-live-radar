import { useTranslation } from 'react-i18next'

import { deleteEvent } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import { TYPE_COLORS } from '@/theme'
import type { RawEventLink, TargetType } from '@/types'

const colorOf = (type: string | null | undefined) =>
  type != null && type in TYPE_COLORS ? TYPE_COLORS[type as TargetType] : TYPE_COLORS.unknown

/** One T{track}/M{sighting} chip. The type shown is the TRACK's — that is what
 * the map draws — with this message's own reading kept beside it whenever the
 * two disagree, which is the case worth seeing: it means something corrected
 * the track after this message was parsed.
 *
 * The T code is the button: clicking it opens the whole track for editing. */
export default function EventChip({
  event,
  onOpenTrack,
  onDropped,
}: {
  event: RawEventLink
  onOpenTrack: () => Promise<unknown>
  onDropped: () => void
}) {
  const { t } = useTranslation()
  const trackType = event.threat_target_type ?? event.target_type
  const differs =
    event.target_type != null &&
    event.threat_target_type != null &&
    event.target_type !== event.threat_target_type

  return (
    <span className="inline-flex items-center gap-1 rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: colorOf(trackType) }}
      />
      {trackType && <span className="text-slate-300">{t(`target.${trackType}`)}</span>}
      {differs && (
        <span className="text-slate-600" title="Як прочитало це повідомлення">
          ←{t(`target.${event.target_type}`)}
        </span>
      )}
      {event.district_name && <span className="text-slate-300">{event.district_name}</span>}
      <button
        onClick={() => void onOpenTrack().catch(() => {})}
        title="Відкрити трек для редагування"
        className="opacity-70 underline decoration-dotted underline-offset-2 hover:text-slate-200 hover:opacity-100"
      >
        T{event.threat_id}
      </button>
      <span className="opacity-70">M{event.event_id}</span>
      {event.incident_id != null && <span className="text-slate-500">I{event.incident_id}</span>}
      {event.corroboration_count != null && (
        <span className="text-slate-500">
          {event.corroboration_count} {t('log.corroboration')}
        </span>
      )}
      {event.confidence != null && (
        <span className="text-slate-500">{Math.round(event.confidence * 100)}%</span>
      )}
      <AdminActionButton
        label="×"
        title="Зняти подію з повідомлення"
        tone="danger"
        compact
        confirm={`Зняти подію M${event.event_id} з треку T${event.threat_id}? Якщо вона в треку остання, трек буде скасовано.`}
        onRun={() => deleteEvent(event.event_id).then(onDropped)}
      />
    </span>
  )
}
