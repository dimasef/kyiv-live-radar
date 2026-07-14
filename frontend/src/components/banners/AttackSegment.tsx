import { Crosshair, Flame, Ghost, MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { threatGlyphSvg } from '../../threatIcons'
import type { Incident } from '../../types'
import Collapsible from './Collapsible'

export default function AttackSegment({
  incident,
  color,
  open,
}: {
  incident: Incident
  color: string
  open: boolean
}) {
  const { t } = useTranslation()

  const hypersonic =
    incident.has_hypersonic && incident.classification === 'ballistic'
      ? ` (${t('attack.hypersonic')})`
      : ''

  const counts = [
    { n: incident.track_count, Icon: Crosshair, title: t('incident.targets') },
    { n: incident.impact_count, Icon: Flame, title: t('incident.impacts') },
    { n: incident.district_count, Icon: MapPin, title: t('incident.districts') },
  ].filter((c) => c.n > 0)

  return (
    <div className="flex min-w-0 items-center">
      <Collapsible open={open}>
        <span className="flex items-center gap-1.5 pr-1.5 sm:gap-2 sm:pr-2">
          <span className="min-w-0 truncate uppercase tracking-wide">
            {t(`attack.classification.${incident.classification}`)}
            {hypersonic}
          </span>
          {incident.decoy_suspected && (
            <span className="flex-none opacity-80" title={t('attack.decoySuspected')}>
              <Ghost size={13} aria-label={t('attack.decoySuspected')} />
            </span>
          )}
          <span className="flex flex-none items-center gap-1.5 font-mono text-[10.5px] font-medium tabular-nums opacity-90 sm:text-[12px]">
            {counts.map(({ n, Icon, title }) => (
              <span key={title} className="flex items-center gap-0.5" title={title}>
                <Icon size={12} className="flex-none" />
                {n}
              </span>
            ))}
          </span>
        </span>
      </Collapsible>
      <span
        className="flex-none leading-none"
        aria-hidden
        dangerouslySetInnerHTML={{
          __html: threatGlyphSvg(incident.target_type, { size: 18, color, state: 'active' }),
        }}
      />
    </div>
  )
}
