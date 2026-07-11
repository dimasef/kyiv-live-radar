import { CheckCircle2, Crosshair, Info, RadioTower, ShieldCheck, TriangleAlert } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../store'
import { STATUS_COLORS, threatColor } from '../theme'
import type { FeedEntry, Notice } from '../types'

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

// One all-clear announced across channels within this window is ONE event —
// collapse the notices into a single card instead of repeating it per source.
const CLEAR_GROUP_MS = 12 * 60 * 1000

/** Cluster the notices timeline: adjacent all-clears within the window become
 * one unit (several sources, one "відбій"); every other notice stays its own. */
function clusterNotices(notices: Notice[]): Notice[][] {
  const units: Notice[][] = []
  for (const n of notices) {
    const last = units[units.length - 1]
    const joins =
      n.kind === 'clear' &&
      last != null &&
      last[0].kind === 'clear' &&
      Math.abs(new Date(last[0].event_time).getTime() - new Date(n.event_time).getTime()) <=
        CLEAR_GROUP_MS
    if (joins) last.push(n)
    else units.push([n])
  }
  return units
}

/** An info entry in the feed timeline: an all-clear or an attack summary —
 * important to see, but not a live threat. A multi-source all-clear renders as
 * one card with all its source badges, not one card per channel. */
function renderNoticeUnit(notices: Notice[], t: (k: string) => string): ReactNode {
  const head = notices[0]
  const isClear = head.kind === 'clear'
  const color = isClear ? STATUS_COLORS.clear : '#38bdf8'
  const Icon = isClear ? ShieldCheck : Info
  const sources = Array.from(new Set(notices.map((n) => n.source_name).filter(Boolean)))
  return (
    <li
      className="feed-item rounded-lg border px-2.5 py-2 text-xs backdrop-blur-sm"
      style={{
        borderColor: `${color}22`,
        borderLeft: `2px solid ${color}`,
        background: `${color}0d`,
        boxShadow: `inset 2px 0 10px -4px ${color}55`,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className="flex items-center gap-1.5 font-semibold uppercase tracking-wide"
          style={{ color }}
        >
          <Icon size={12} className="flex-none" />
          {t(`notice.${head.kind}`)}
          {notices.length > 1 && (
            <span className="font-mono font-semibold" style={{ color }}>
              ×{notices.length}
            </span>
          )}
        </span>
        <EventTime iso={head.event_time} />
      </div>
      <div className="mt-0.5 break-words leading-snug text-slate-300">{head.text}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {sources.length > 0 ? (
          sources.map((name) => <SourceBadge key={name} name={name} t={t} />)
        ) : (
          <SourceBadge name={head.source_name} t={t} />
        )}
      </div>
    </li>
  )
}

export default function ThreatLog() {
  const { t, i18n } = useTranslation()
  const log = useRadar((s) => s.log)
  const districts = useRadar((s) => s.districts)
  const inspectedThreat = useRadar((s) => s.inspectedThreat)
  const inspectThreat = useRadar((s) => s.inspectThreat)
  const clearInspection = useRadar((s) => s.clearInspection)
  const notices = useRadar((s) => s.notices)

  // Merge sighting groups and info notices into one time-sorted timeline;
  // multi-source all-clears are clustered into one unit.
  type Item =
    | { kind: 'group'; time: string; keyId: string; group: FeedEntry[] }
    | { kind: 'notice'; time: string; keyId: string; notices: Notice[] }
  const timeline: Item[] = [
    ...groupFeed(log).map(
      (g): Item => ({ kind: 'group', time: g[0].event.event_time, keyId: `g${g[0].event.id}`, group: g }),
    ),
    ...clusterNotices(notices).map(
      (u): Item => ({ kind: 'notice', time: u[0].event_time, keyId: `n${u[0].id}`, notices: u }),
    ),
  ].sort((a, b) => (a.time < b.time ? 1 : -1))

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

            if (item.kind === 'notice') {
              return (
                <Fragment key={item.keyId}>
                  {separator}
                  {renderNoticeUnit(item.notices, t)}
                </Fragment>
              )
            }

            const group = item.group
            const head = group[0]
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
                      <span className="flex items-center gap-1.5 font-medium text-slate-100">
                        {threat.status === 'impact' && (
                          <span
                            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                            style={{
                              color: STATUS_COLORS.impact,
                              background: `${STATUS_COLORS.impact}1a`,
                            }}
                          >
                            <Crosshair size={10} className="flex-none" />
                            {t('log.impact')}
                          </span>
                        )}
                        {!(threat.status === 'impact' && threat.target_type === 'unknown') &&
                          t(`target.${threat.target_type}`)}
                        {(() => {
                          // Count KNOWN AS OF this event (running-max at the time),
                          // not the track's final count — so an early "Ціль на
                          // місто!" doesn't retroactively show the ×3 that only a
                          // later "3 ракети" established. Fall back to the track's
                          // current count for pre-column events (null).
                          const count = event.event_target_count ?? threat.target_count
                          return count > 1 ? (
                            <span className="ml-1 font-mono font-semibold text-amber-300">
                              ×{count}
                            </span>
                          ) : null
                        })()}
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
            // Green accent (same as legend.clear) — this card is good news,
            // it's reporting resolved/closed tracks, not a live sighting.
            const closedColor = STATUS_COLORS.clear
            return (
              <Fragment key={`group-${head.event.id}`}>
                {separator}
                <li
                  className="feed-item rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] px-2.5 py-2 text-xs backdrop-blur-sm"
                  style={{
                    borderLeft: `2px solid ${closedColor}`,
                    boxShadow: `inset 2px 0 10px -4px ${closedColor}55`,
                  }}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="flex items-center gap-1.5 font-medium text-emerald-300">
                      <CheckCircle2 size={12} className="flex-none" />
                      {t('log.closedMultiple')}
                      <span className="font-mono font-semibold text-emerald-200">
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
