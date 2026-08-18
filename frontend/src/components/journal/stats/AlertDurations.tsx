import { useTranslation } from 'react-i18next'

import type { DurationBucket } from '@/types'

import ColumnChart from './charts/ColumnChart'
import { formatHours } from './statsMath'

interface Props {
  buckets: DurationBucket[]
  medianSeconds: number
  meanSeconds: number
  longestSeconds: number
}

/** "How long do I usually sit in the shelter": the alert-duration histogram over
 * ordered bins, plus the median (the honest middle) next to the mean. Only
 * complete windows count — an open or failsafe-closed alert has no duration. */
export default function AlertDurations({
  buckets,
  medianSeconds,
  meanSeconds,
  longestSeconds,
}: Props) {
  const { t } = useTranslation()
  const total = buckets.reduce((n, b) => n + b.count, 0)
  if (!total) return null

  return (
    <div>
      <div className="panel-title mb-2">{t('journal.stats.durations')}</div>
      <ColumnChart
        columns={buckets.map((b) => ({
          key: b.bucket,
          label: t(`journal.stats.bucket.${b.bucket}`),
          value: b.count,
        }))}
        format={(v) => String(v)}
        heightClass="h-24"
        tableLabel={t('journal.stats.durations')}
        valueHeader={t('journal.stats.alertCount')}
      />
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        {t('journal.stats.median')}{' '}
        <span className="font-mono tabular-nums text-slate-300">{formatHours(medianSeconds)}</span>
        {' · '}
        {t('journal.stats.mean')}{' '}
        <span className="font-mono tabular-nums text-slate-400">{formatHours(meanSeconds)}</span>
        {' · '}
        {t('journal.longest')}{' '}
        <span className="font-mono tabular-nums text-slate-400">{formatHours(longestSeconds)}</span>
      </p>
    </div>
  )
}
