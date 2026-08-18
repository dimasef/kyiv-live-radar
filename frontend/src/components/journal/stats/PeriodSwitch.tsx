import { useTranslation } from 'react-i18next'

import type { AnalyticsPeriod } from '@/types'

import { PERIODS } from './statsMath'

/** The one filter row for the whole tab — every chart below re-renders against
 * the same slice, so there are no per-chart filters. */
export default function PeriodSwitch({
  value,
  onChange,
  disabled,
}: {
  value: AnalyticsPeriod
  onChange: (period: AnalyticsPeriod) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div role="group" aria-label={t('journal.stats.period')} className="flex gap-1">
      {PERIODS.map((period) => (
        <button
          key={period}
          onClick={() => onChange(period)}
          disabled={disabled}
          aria-pressed={period === value}
          className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors disabled:opacity-50 ${
            period === value
              ? 'bg-phosphor/15 text-phosphor-soft'
              : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          {t(`journal.stats.periods.${period}`)}
        </button>
      ))}
    </div>
  )
}
