import { CloudOff, Siren } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import type { Alert } from '@/types'
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
  const zone = useRadar((s) => (alert.zone_id ? s.zones[alert.zone_id] : undefined))

  // A raion alert names its raion; the official channel's city/oblast ones have
  // a fixed label. The zone state may not have arrived yet, in which case the
  // generic wording is still true, just less specific.
  const label =
    alert.scope === 'raion' && zone
      ? compact
        ? zone.name_uk.replace(/\s+район$/, '')
        : t('alert.scope.raion', { name: zone.name_uk })
      : t(compact ? `alert.short.${alert.scope}` : `alert.scope.${alert.scope}`)

  // The district provider has gone quiet. The siren may well still be running,
  // but the running clock beside it is no longer something we can vouch for, so
  // say so rather than let it tick on unqualified.
  const staleSource = zone?.stale === true

  return (
    <div className="flex flex-none items-center">
      <Siren size={15} className="flex-none animate-pulse" />
      <Collapsible open={open}>
        <span className="pl-1.5 uppercase tracking-wide sm:pl-2">{label}</span>
      </Collapsible>
      {staleSource ? (
        <span className="flex flex-none items-center gap-1 pl-1.5 opacity-75 sm:pl-2">
          <CloudOff size={13} aria-hidden />
          <span className="sr-only">{t('alert.staleSource')}</span>
        </span>
      ) : (
        <span className="pl-1.5 font-mono text-[11px] tabular-nums opacity-90 sm:pl-2 sm:text-[12px]">
          {formatDuration(now - new Date(alert.started_at).getTime())}
        </span>
      )}
    </div>
  )
}
