import { ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import { INCIDENT_SEVERITY_COLOR, STATUS_COLORS } from '../../theme'
import AlertSegment from './AlertSegment'
import AttackSegment from './AttackSegment'
import BannerShell from './BannerShell'
import Collapsible from './Collapsible'
import Presence from './Presence'
import { CLEAR_LINGER_MS, mostRecentlyEnded, notableIncident, primaryAlert, useNow } from './status'

export default function StatusBanner() {
  const { t } = useTranslation()
  const alerts = useRadar((s) => s.alerts)
  const incidents = useRadar((s) => s.incidents)

  const [collapsed, setCollapsed] = useState(false)
  const toggle = () => setCollapsed((v) => !v)
  const toggleLabel = t(collapsed ? 'banner.expand' : 'banner.collapse')

  const alert = primaryAlert(alerts)
  const incident = notableIncident(incidents)
  const ended = mostRecentlyEnded(alerts)

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
