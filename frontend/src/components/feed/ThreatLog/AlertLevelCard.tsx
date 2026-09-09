import { Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { regionLabel } from '@/lib/regions'
import { useRadar } from '@/store'
import { STATUS_COLORS, TYPE_COLORS } from '@/theme'
import type { Notice } from '@/types'

import { DevId, EventTime } from './badges'

/** The threat level moving inside a running alert, drawn as the alert card it
 * effectively is: «Дронова небезпека» becoming «Ракетна загроза» is a new
 * threat announced over the same siren, and the reader wants it said the way
 * the siren was — the threat's name, where, and the same instruction.
 *
 * The backend files the level it moved TO under the matching target family
 * (missile / shahed — see pipeline/ingest/alert.py), which picks both the name
 * and the colour: the red of a missile alert, or the yellow the forecast card
 * speaks drones in. A family the client cannot name falls back to the plain
 * «Повітряна тривога» in the level-less red. */
export default function AlertLevelCard({ notice }: { notice: Notice }) {
  const { t } = useTranslation()
  const regions = useRadar((s) => s.regions)

  const missile = notice.target_type === 'missile'
  const drone = notice.target_type === 'shahed'
  const threatKey = missile
    ? 'alert.threat.missile'
    : drone
      ? 'alert.threat.drone'
      : 'alert.threat.unspecified'
  const color = drone ? TYPE_COLORS.shahed : STATUS_COLORS.confirmed
  // The official channel speaks for the city, so a Kyiv notice is «м. Київ»;
  // any other region is named as the catalogue names it.
  const where =
    notice.region === 'kyiv' ? t('notice.alertWhereCity') : regionLabel(regions, notice.region)
  const threat = t(threatKey)

  return (
    <li
      className="feed-item rounded-xl border px-3 py-2.5 text-xs"
      style={{
        borderColor: 'rgba(255,255,255,.06)',
        borderLeft: `2px solid ${color}`,
        background: `${color}0f`,
      }}
    >
      <div className="flex items-center justify-between gap-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <Siren size={16} className="flex-none" style={{ color }} />
          <div className="min-w-0">
            <div
              className="text-[12.5px] font-bold uppercase tracking-[0.09em]"
              style={{ color }}
            >
              {threat}
            </div>
            <div className="mt-px truncate text-[10.5px] text-slate-400">{where}</div>
          </div>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          <DevId>N{notice.id}</DevId>
          <EventTime iso={notice.event_time} />
        </div>
      </div>

      <p className="mt-2 break-words leading-snug text-slate-300">
        {t('notice.alertStartBody', { where, threat })}
      </p>
    </li>
  )
}
