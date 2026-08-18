import { useTranslation } from 'react-i18next'

import type { DistrictStat } from '@/types'

import BarList from './charts/BarList'

interface Props {
  districts: DistrictStat[]
  districtName: (id: number) => string
  limit?: number
}

/** Where targets keep showing up. Ranked by the number of DAYS a district saw a
 * target, not by raw sighting count: event volume tracks how talkative the
 * spotters were that night, days don't. Raw sightings ride along dimmed. */
export default function DistrictBars({ districts, districtName, limit = 10 }: Props) {
  const { t } = useTranslation()
  const rows = districts.slice(0, limit)
  if (!rows.length) return null

  return (
    <div>
      <div className="panel-title mb-2.5">{t('journal.stats.topDistricts')}</div>
      <BarList
        rows={rows.map((d) => ({
          key: String(d.district_id),
          label: districtName(d.district_id),
          value: d.days,
          detail: `${d.events}`,
        }))}
        format={(v) => t('journal.stats.dayCount', { count: v })}
      />
      <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
        {t('journal.stats.districtNote')}
      </p>
    </div>
  )
}
