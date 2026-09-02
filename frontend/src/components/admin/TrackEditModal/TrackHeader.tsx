import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { dismissThreat, restoreThreat, setThreatType } from '@/api'
import AdminActionButton from '@/components/admin/AdminActionButton'
import { threatChip } from '@/threatLabels'
import type { TargetType, Threat } from '@/types'

import { ADMIN_TARGET_TYPES } from '../adminLayout'
import TrackCountStepper from './TrackCountStepper'

/** What the track IS — its identity line, and the three properties an operator
 * fixes without touching any individual sighting: type, group size, lifecycle.
 *
 * The lifecycle comes from `threatChip`, the same source the map popup and the
 * feed read, so one state never has two names. The raw `closed_reason` used to
 * be printed here verbatim, which showed a Ukrainian operator «stand_down». */
export default function TrackHeader({
  track,
  onClose,
  onChanged,
}: {
  track: Threat
  onClose: () => void
  onChanged: (track: Threat) => void
}) {
  const { t } = useTranslation()
  const open = track.closed_at == null
  const chip = threatChip(track)

  return (
    <div className="shrink-0 border-b border-white/[0.06] px-4 pt-3 pb-3 sm:px-5 sm:pt-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="font-display text-sm font-bold text-slate-100">
            Трек <span className="font-mono">T{track.id}</span>
          </h2>
          <span
            className="flex-none rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: chip.color, background: `${chip.color}1a` }}
          >
            {t(chip.labelKey)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="-mr-1 inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
          aria-label="Закрити"
        >
          <X size={18} />
        </button>
      </div>

      <p className="mt-0.5 font-mono text-[10px] text-slate-500">
        {track.events.length} под. · {track.corroboration_count} дж. ·{' '}
        {Math.round(track.confidence * 100)}%
        {track.incident_id != null && <> · I{track.incident_id}</>}
      </p>

      {/* Two rows on a phone, one on a desktop: the type select needs room to
          show «Реактивний БПЛА» without truncating, and cramming the stepper
          and the lifecycle button beside it left all three too narrow to hit. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={track.target_type}
          onChange={(e) => {
            void setThreatType(track.id, e.target.value as TargetType)
              .then(onChanged)
              .catch(() => {})
          }}
          className="h-9 min-w-0 flex-1 rounded-lg border border-white/15 bg-ink-900 px-2 text-xs text-slate-200 sm:flex-none"
          aria-label="Тип цілі треку"
        >
          {ADMIN_TARGET_TYPES.map((tt) => (
            <option key={tt} value={tt}>
              {t(`target.${tt}`)}
            </option>
          ))}
        </select>
        <TrackCountStepper track={track} onChanged={onChanged} />
        <div className="w-full sm:w-auto">
          {open ? (
            <AdminActionButton
              label="Скасувати ціль"
              tone="danger"
              confirm="Скасувати цю ціль? Вона зникне з мапи та статистики."
              onRun={() => dismissThreat(track.id).then(onChanged)}
            />
          ) : (
            <AdminActionButton
              label="Повернути ціль"
              onRun={() => restoreThreat(track.id).then(onChanged)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
