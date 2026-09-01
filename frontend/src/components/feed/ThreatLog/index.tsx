import { Fragment, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { currentRegion, effectiveRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import { shownRegions } from '@/store/feedRegions'
import { FEED_ZOOM } from '@/store/prefsSlice'

import OnlineBadge from '../OnlineBadge'
import AlertCard from './AlertCard'
import AttackSummaryCard from './AttackSummaryCard'
import ClosedGroupCard from './ClosedGroupCard'
import DaySeparator from './DaySeparator'
import NoticeCard from './NoticeCard'
import ThreatCard from './ThreatCard'
import {
  buildTimeline,
  filterFeedAlerts,
  filterFeedIncidents,
  filterFeedNotices,
  filterFeedRegions,
  kyivDayKey,
} from './timeline'

export default function ThreatLog() {
  const { t } = useTranslation()
  const log = useRadar((s) => s.log)
  const notices = useRadar((s) => s.notices)
  const recentIncidents = useRadar((s) => s.recentIncidents)
  const alerts = useRadar((s) => s.alerts)
  const homeZoneId = useRadar((s) => s.homeZoneId)
  const feedTextSize = useRadar((s) => s.feedTextSize)
  const feedExtraRegions = useRadar((s) => s.feedExtraRegions)
  const regions = useRadar((s) => s.regions)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  // The server already narrowed the page it loaded; this narrows what the live
  // WebSocket keeps pushing on top of it.
  const shown = useMemo(
    () =>
      new Set(shownRegions(feedExtraRegions, currentRegion({ regions, chosenRegion }))),
    [feedExtraRegions, regions, chosenRegion],
  )
  // Alerts are narrowed by RAION, not by the shown regions — see
  // filterFeedAlerts.
  const alertCtx = useMemo(
    () => ({ zoneId: homeZoneId, region: effectiveRegion(regions, chosenRegion) }),
    [homeZoneId, regions, chosenRegion],
  )
  // Grouping up to 250 entries plus notices, incidents and alerts — pure, and
  // only these inputs move it, so it must not re-run on an unrelated re-render.
  const timeline = useMemo(
    () =>
      buildTimeline(
        filterFeedRegions(log, shown),
        filterFeedNotices(notices, shown),
        filterFeedIncidents(recentIncidents, shown),
        filterFeedAlerts(alerts, alertCtx),
      ),
    [log, shown, notices, recentIncidents, alerts, alertCtx],
  )

  const dayKeys = useMemo(
    () => timeline.map((item) => kyivDayKey(new Date(item.time))),
    [timeline],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 hidden items-center justify-between lg:flex">
        <span className="panel-title">{t('log.title')}</span>
        <OnlineBadge />
      </div>

      {timeline.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
          <div className="radar radar--rings h-16 w-16 opacity-70" aria-hidden />
          <div className="font-mono text-xs text-slate-500">{t('log.empty')}</div>
        </div>
      ) : (
        <ul
          className="scroll-slim min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1"
          // CSS zoom (not font-size): the cards' text uses absolute Tailwind
          // sizes, so only zoom scales text and layout together.
          style={{ zoom: FEED_ZOOM[feedTextSize] }}
        >
          {timeline.map((item, i) => {
            // dayKeys is precomputed alongside the timeline: reading the
            // previous row's key here recomputed kyivDayKey twice per row.
            const dayKey = dayKeys[i]
            const separator = dayKey !== dayKeys[i - 1] ? <DaySeparator dayKey={dayKey} /> : null

            if (item.kind === 'notice') {
              return (
                <Fragment key={item.keyId}>
                  {separator}
                  <NoticeCard notices={item.notices} />
                </Fragment>
              )
            }

            if (item.kind === 'alertStart' || item.kind === 'alertEnd') {
              return (
                <Fragment key={item.keyId}>
                  {separator}
                  <AlertCard alert={item.alert} ended={item.kind === 'alertEnd'} />
                </Fragment>
              )
            }

            if (item.kind === 'incidentEnd') {
              return (
                <Fragment key={item.keyId}>
                  {separator}
                  <AttackSummaryCard incident={item.incident} />
                </Fragment>
              )
            }

            // A group holds every event from ONE source message. That covers
            // two very different shapes: (a) a "дорозвідка"/stand-down that
            // closed SEVERAL tracks at once — one event per closed track, so
            // MULTIPLE distinct track ids; (b) a single sighting/impact that
            // named SEVERAL districts — one event per district but all on the
            // SAME track. Only (a) is "Закрито цілей"; (b) is a normal sighting
            // and must NOT be shown as closed. Distinguish by distinct track
            // count, not group length.
            const distinctTracks = new Set(item.group.map((e) => e.threat.id)).size
            return (
              <Fragment key={item.keyId}>
                {separator}
                {distinctTracks > 1 ? (
                  <ClosedGroupCard group={item.group} />
                ) : (
                  <ThreatCard event={item.group[0].event} threat={item.group[0].threat} />
                )}
              </Fragment>
            )
          })}
        </ul>
      )}
    </div>
  )
}
