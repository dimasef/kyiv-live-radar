import { ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { effectiveRegion } from '@/lib/regions'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

import { useRadar } from '@/store'
import { INCIDENT_SEVERITY_COLOR, STATUS_COLORS } from '@/theme'
import AlertSegment from './AlertSegment'
import AttackSegment from './AttackSegment'
import BannerShell from './BannerShell'
import Collapsible from './Collapsible'
import Presence from './Presence'
import { alertCoversMe, primaryAlert } from './coverage'
import {
  CLEAR_LINGER_MS,
  type CollapsedFor,
  mostRecentlyEnded,
  notableIncident,
  inFollowedRegion,
  stillCollapsed,
  useNow,
} from './status'

function loadCollapsedFor(): CollapsedFor | null {
  const raw = safeGet(STORAGE_KEYS.bannerCollapsed)
  if (!raw) return null
  try {
    return JSON.parse(raw) as CollapsedFor
  } catch {
    return null
  }
}

export default function StatusBanner() {
  const { t } = useTranslation()
  const alerts = useRadar((s) => s.alerts)
  const incidents = useRadar((s) => s.incidents)
  const regions = useRadar((s) => s.regions)
  const chosenRegion = useRadar((s) => s.chosenRegion)
  const homeZoneId = useRadar((s) => s.homeZoneId)

  // Narrowed before anything is picked, so the banner can only ever speak
  // about where this reader actually is — their raion for an alert (see
  // coverage.ts), their oblast for an attack.
  const ctx = { zoneId: homeZoneId, region: effectiveRegion(regions, chosenRegion) }
  const mine = alerts.filter((a) => alertCoversMe(a, ctx))
  const alert = primaryAlert(mine)
  const incident = notableIncident(inFollowedRegion(incidents, regions, chosenRegion))
  const ended = mostRecentlyEnded(mine)

  const [collapsedFor, setCollapsedFor] = useState(loadCollapsedFor)
  const collapsed = stillCollapsed(collapsedFor, alert?.id ?? null, incident?.id ?? null)
  const toggle = () => {
    const next = collapsed ? null : { alert: alert?.id ?? null, incident: incident?.id ?? null }
    if (next) safeSet(STORAGE_KEYS.bannerCollapsed, JSON.stringify(next))
    else safeRemove(STORAGE_KEYS.bannerCollapsed)
    setCollapsedFor(next)
  }
  const toggleLabel = t(collapsed ? 'banner.expand' : 'banner.collapse')

  const sinceCleared =
    !alert && ended ? Date.now() - new Date(ended.ended_at!).getTime() : Infinity
  const lingering = sinceCleared < CLEAR_LINGER_MS

  const now = useNow(!!alert || lingering)

  const color = incident
    ? incident.target_type === 'ballistic'
      ? INCIDENT_SEVERITY_COLOR.ballistic
      : INCIDENT_SEVERITY_COLOR.other
    : STATUS_COLORS.confirmed

  let content: ReactNode = null
  if (alert || incident) {
    content = (
      <BannerShell
        tone={incident ? 'attack' : 'alert'}
        color={color}
        role="alert"
        label={toggleLabel}
        expanded={!collapsed}
        onToggle={toggle}
      >
        {alert && <AlertSegment alert={alert} now={now} open={!collapsed} compact={!!incident} />}
        {alert && incident && (
          <span className="h-4 w-px flex-none bg-current opacity-25" aria-hidden />
        )}
        {incident && <AttackSegment incident={incident} color={color} open={!collapsed} />}
      </BannerShell>
    )
  } else if (lingering) {
    content = (
      <BannerShell
        tone="clear"
        color={STATUS_COLORS.clear}
        role="status"
        label={toggleLabel}
        expanded={!collapsed}
        onToggle={toggle}
      >
        <ShieldCheck size={15} className="flex-none" />
        <Collapsible open={!collapsed}>
          <span className="pl-1.5 uppercase tracking-wide sm:pl-2">{t('alert.clear')}</span>
        </Collapsible>
      </BannerShell>
    )
  }

  return <Presence visible={!!alert || !!incident || lingering}>{content}</Presence>
}
