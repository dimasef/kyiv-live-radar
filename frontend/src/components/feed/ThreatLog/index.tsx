import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import ClosedGroupCard from './ClosedGroupCard'
import DaySeparator from './DaySeparator'
import NoticeCard from './NoticeCard'
import ThreatCard from './ThreatCard'
import { buildTimeline, kyivDayKey } from './timeline'

export default function ThreatLog() {
  const { t } = useTranslation()
  const log = useRadar((s) => s.log)
  const notices = useRadar((s) => s.notices)
  const timeline = buildTimeline(log, notices)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="panel-title mb-2 hidden lg:block">{t('log.title')}</div>

      {timeline.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
          <div className="radar radar--rings h-16 w-16 opacity-70" aria-hidden />
          <div className="font-mono text-xs text-slate-500">{t('log.empty')}</div>
        </div>
      ) : (
        <ul className="scroll-slim min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {timeline.map((item, i) => {
            const dayKey = kyivDayKey(new Date(item.time))
            const prevDayKey = i > 0 ? kyivDayKey(new Date(timeline[i - 1].time)) : null
            const separator = dayKey !== prevDayKey ? <DaySeparator dayKey={dayKey} /> : null

            if (item.kind === 'notice') {
              return (
                <Fragment key={item.keyId}>
                  {separator}
                  <NoticeCard notices={item.notices} />
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
