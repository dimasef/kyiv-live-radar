import { Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { Alert } from '../../types'
import Collapsible from './Collapsible'
import { formatDuration } from './status'

export default function AlertSegment({
  alert,
  now,
  open,
  compact,
}: {
  alert: Alert
  now: number
  open: boolean
  compact: boolean
}) {
  const { t } = useTranslation()
  const label = compact ? t(`alert.short.${alert.scope}`) : t(`alert.scope.${alert.scope}`)

  return (
    <div className="flex flex-none items-center">
      <Siren size={15} className="flex-none animate-pulse" />
      <Collapsible open={open}>
        <span className="pl-1.5 uppercase tracking-wide sm:pl-2">{label}</span>
      </Collapsible>
      <span className="pl-1.5 font-mono text-[11px] tabular-nums opacity-90 sm:pl-2 sm:text-[12px]">
        {formatDuration(now - new Date(alert.started_at).getTime())}
      </span>
    </div>
  )
}
