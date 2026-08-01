import { useTranslation } from 'react-i18next'

import type { ThreatAxis } from '@/types'

export default function AxisLabel({ axis, color }: { axis: ThreatAxis; color: string }) {
  const { t } = useTranslation()
  const typeLabel = t(`target.${axis.target_type}`, axis.target_type)
  const origin = axis.origin_name ?? t(`axisSector.${axis.sector}`, axis.sector)
  const corroborated = axis.status === 'corroborated'
  return (
    <div
      className="mt-0.5 whitespace-nowrap rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium leading-tight"
      style={{ color }}
    >
      {typeLabel} · {origin}
      {corroborated ? (
        <span className="ml-1 opacity-70">×{axis.corroboration_count}</span>
      ) : (
        <span className="ml-1 opacity-60">{t('axis.unverified')}</span>
      )}
    </div>
  )
}

export const WRAP =
  'pointer-events-none absolute z-[850] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center transition-opacity duration-300'
