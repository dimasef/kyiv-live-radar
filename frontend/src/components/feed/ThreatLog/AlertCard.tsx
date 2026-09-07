import { Clock, ShieldCheck, Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { alertLevelColor, alertThreatKey } from '@/lib/alertLevel'
import { durationLabel } from '@/lib/duration'
import { useRadar } from '@/store'
import { STATUS_COLORS } from '@/theme'
import type { Alert } from '@/types'

import { DevId, EventTime } from './badges'

/** An air-raid alert opening or closing, as a feed entry.
 *
 * The banner has always shown the alert, but the banner is one line that
 * disappears; scrolling the Стрічка подій back afterwards showed the sightings
 * and the відбій with nothing marking when the siren actually started. The
 * all-clear got a card long ago (`AllClearCard`, raised from the official
 * channel's own message) — this is the other half, and it also covers raion
 * alerts, which have no channel message to be a Notice.
 *
 * `AllClearCard` still owns the official channel's «Відбій»: it is the louder,
 * hand-tuned card and it has the source's own words. This one's `ended` mode
 * exists for raion alerts, which that path never produces.
 */
export default function AlertCard({ alert, ended }: { alert: Alert; ended: boolean }) {
  const { t } = useTranslation()
  const zone = useRadar((s) => (alert.zone_id ? s.zones[alert.zone_id] : undefined))

  // The opening card is coloured by the level it announced — жовтий for a drone
  // alert, червоний for a missile one — so the feed reads the same way the map
  // does when scrolled back later.
  //
  // …unless the level has since MOVED. `Alert.level` is the level running now,
  // not the one this card's moment announced (an escalation rewrites the row
  // rather than opening a second alert — see the backend's `_relevel`), and a
  // card sitting at 21:00 must not retroactively claim a missile threat that
  // was declared at 21:12. The change has its own card; this one falls back to
  // the level-less wording rather than name a threat it cannot vouch for.
  const relevelled = alert.level_changed_at != null
  const threatKey = relevelled ? 'alert.threat.unspecified' : alertThreatKey(alert)
  const color = ended
    ? STATUS_COLORS.clear
    : relevelled
      ? STATUS_COLORS.confirmed
      : alertLevelColor(alert)
  const Icon = ended ? ShieldCheck : Siren
  const where =
    zone?.name_uk ??
    t(alert.scope === 'oblast' ? 'notice.alertWhereOblast' : 'notice.alertWhereCity')

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
          <Icon size={16} className="flex-none" style={{ color }} />
          <div className="min-w-0">
            <div
              className="text-[12.5px] font-bold uppercase tracking-[0.09em]"
              style={{ color }}
            >
              {ended ? t('notice.alertEnded') : t(threatKey)}
            </div>
            <div className="mt-px truncate text-[10.5px] text-slate-400">{where}</div>
          </div>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          <DevId>A{alert.id}</DevId>
          <EventTime iso={ended ? alert.ended_at! : alert.started_at} />
        </div>
      </div>

      <p className="mt-2 break-words leading-snug text-slate-300">
        {ended
          ? t('notice.alertEndedBody', { where })
          : t('notice.alertStartBody', { where, threat: t(threatKey) })}
      </p>

      {ended && (
        <span
          className="mt-2.5 inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-1.5 py-0.5 font-mono text-[10px]"
          style={{ background: `${color}1f`, color }}
        >
          <Clock size={10} className="flex-none" />
          {t('notice.clearLasted')} {durationLabel(t, alert.started_at, alert.ended_at!)}
        </span>
      )}
    </li>
  )
}
