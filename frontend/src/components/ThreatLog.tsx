import { RadioTower, TriangleAlert } from 'lucide-react'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../store'
import { threatColor } from '../theme'
import type { FeedEntry } from '../types'

const KYIV_TZ = 'Europe/Kyiv'

// YYYY-MM-DD in Kyiv's calendar day, not UTC/browser-local — a message right
// after midnight Kyiv time must group under that new day, not the UTC one.
function kyivDayKey(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: KYIV_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function daySeparatorLabel(dayKey: string, lang: string, t: (k: string) => string): string {
  const now = new Date()
  if (dayKey === kyivDayKey(now)) return t('log.today')
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  if (dayKey === kyivDayKey(yesterday)) return t('log.yesterday')
  const label = new Intl.DateTimeFormat(lang === 'uk' ? 'uk-UA' : 'en-US', {
    timeZone: KYIV_TZ,
    day: 'numeric',
    month: 'long',
  }).format(new Date(`${dayKey}T12:00:00Z`))
  return label.charAt(0).toUpperCase() + label.slice(1)
}

// One real message can close several tracks at once (e.g. an untyped
// "Дорозвідка" stand-down) — each gets its own ThreatEvent so it shows up in
// ITS OWN track's inspect view, but that means the SAME raw text would
// otherwise appear as several back-to-back cards in the flat feed, reading
// as a duplicate. Collapse adjacent entries that came from one source
// message into a single card instead.
function groupFeed(log: FeedEntry[]): FeedEntry[][] {
  const groups: FeedEntry[][] = []
  for (const entry of log) {
    const head = groups[groups.length - 1]?.[0]
    const sameMessage =
      head != null &&
      head.event.source_message_id != null &&
      head.event.source_id === entry.event.source_id &&
      head.event.source_message_id === entry.event.source_message_id &&
      head.event.raw_text === entry.event.raw_text
    if (sameMessage) {
      groups[groups.length - 1].push(entry)
    } else {
      groups.push([entry])
    }
  }
  return groups
}

function EventTime({ iso }: { iso: string }) {
  return (
    <span className="font-mono text-[10px] tabular-nums text-slate-500">
      {new Date(iso).toLocaleTimeString('uk-UA', {
        timeZone: 'Europe/Kyiv',
        hour: '2-digit',
        minute: '2-digit',
      })}
    </span>
  )
}

function SourceBadge({ name, t }: { name: string | null; t: (k: string) => string }) {
  return (
    <span
      className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] ${
        name ? 'bg-white/[0.06] text-slate-300' : 'bg-white/[0.03] italic text-slate-500'
      }`}
    >
      <RadioTower size={10} className="flex-none opacity-70" />
      {name ?? t('log.unknownSource')}
    </span>
  )
}

export default function ThreatLog() {
  const { t, i18n } = useTranslation()
  const log = useRadar((s) => s.log)
  const districts = useRadar((s) => s.districts)
  const inspectedThreat = useRadar((s) => s.inspectedThreat)
  const inspectThreat = useRadar((s) => s.inspectThreat)
  const clearInspection = useRadar((s) => s.clearInspection)

  const groups = groupFeed(log)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="panel-title mb-2 hidden lg:block">{t('log.title')}</div>

      {log.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
          <div className="radar radar--rings h-16 w-16 opacity-70" aria-hidden />
          <div className="font-mono text-xs text-slate-500">{t('log.empty')}</div>
        </div>
      ) : (
        <ul className="scroll-slim min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {groups.map((group, i) => {
            const head = group[0]
            const dayKey = kyivDayKey(new Date(head.event.event_time))
            const prevDayKey =
              i > 0 ? kyivDayKey(new Date(groups[i - 1][0].event.event_time)) : null
            const showSeparator = dayKey !== prevDayKey
            const separator = showSeparator && (
              <li aria-hidden className="flex items-center gap-2 px-1 pt-1.5 first:pt-0">
                <span className="h-px flex-1 bg-white/[0.08]" />
                <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
                  {daySeparatorLabel(dayKey, i18n.language, t)}
                </span>
                <span className="h-px flex-1 bg-white/[0.08]" />
              </li>
            )

            if (group.length === 1) {
              const { event, threat } = head
              const color = threatColor(threat)
              const isSelected = inspectedThreat?.id === threat.id
              const toggleInspect = () =>
                isSelected ? clearInspection() : inspectThreat(threat)
              return (
                <Fragment key={event.id}>
                  {separator}
                  <li
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    onClick={toggleInspect}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        toggleInspect()
                      }
                    }}
                    className={`feed-item cursor-pointer rounded-lg border px-2.5 py-2 text-xs backdrop-blur-sm transition-colors duration-200 ${
                      isSelected
                        ? 'border-white/20 bg-white/[0.09]'
                        : 'border-white/[0.05] bg-white/[0.03] hover:bg-white/[0.06]'
                    }`}
                    style={{
                      borderLeft: `2px solid ${color}`,
                      boxShadow: isSelected
                        ? `inset 2px 0 8px -4px ${color}55, 0 0 0 1px ${color}55`
                        : `inset 2px 0 8px -4px ${color}55`,
                    }}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-medium text-slate-100">
                        {t(`target.${threat.target_type}`)}
                        {threat.target_count > 1 && (
                          <span className="ml-1 font-mono font-semibold text-amber-300">
                            ×{threat.target_count}
                          </span>
                        )}
                      </span>
                      <EventTime iso={event.event_time} />
                    </div>

                    <div className="mt-0.5 break-words leading-snug text-slate-300">
                      {event.raw_text}
                    </div>

                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <SourceBadge name={event.source_name} t={t} />
                      <span className="font-mono text-[10px] tabular-nums text-slate-500">
                        {threat.corroboration_count} {t('log.corroboration')} ·{' '}
                        {Math.round(threat.confidence * 100)}% {t('log.confidence')}
                      </span>
                      {threat.has_conflict && (
                        <span className="flex items-center gap-1 text-[10px] font-medium text-orange-400">
                          <TriangleAlert size={10} className="flex-none" />
                          {t('log.conflict')}
                        </span>
                      )}
                    </div>
                  </li>
                </Fragment>
              )
            }

            // Several tracks closed by ONE real message ("дорозвідка" with no
            // stated type closes every open track at once) — one card, one
            // clickable chip per closed track so each can still be inspected.
            return (
              <Fragment key={`group-${head.event.id}`}>
                {separator}
                <li className="feed-item rounded-lg border border-white/[0.05] bg-white/[0.03] px-2.5 py-2 text-xs backdrop-blur-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium text-slate-100">
                      {t('log.closedMultiple')}
                      <span className="ml-1 font-mono font-semibold text-amber-300">
                        ×{group.length}
                      </span>
                    </span>
                    <EventTime iso={head.event.event_time} />
                  </div>

                  <div className="mt-0.5 break-words leading-snug text-slate-300">
                    {head.event.raw_text}
                  </div>

                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {group.map(({ event, threat }) => {
                      const color = threatColor(threat)
                      const districtName =
                        districts.find((d) => d.id === event.district_id)?.name_uk ?? '?'
                      const isSelected = inspectedThreat?.id === threat.id
                      return (
                        <button
                          key={threat.id}
                          onClick={() =>
                            isSelected ? clearInspection() : inspectThreat(threat)
                          }
                          className="rounded-md px-1.5 py-0.5 text-[10px] font-medium transition-shadow duration-200"
                          style={{
                            background: `${color}22`,
                            color,
                            boxShadow: isSelected ? `0 0 0 1px ${color}` : undefined,
                          }}
                        >
                          {districtName}
                        </button>
                      )
                    })}
                  </div>

                  <div className="mt-1.5">
                    <SourceBadge name={head.event.source_name} t={t} />
                  </div>
                </li>
              </Fragment>
            )
          })}
        </ul>
      )}
    </div>
  )
}
