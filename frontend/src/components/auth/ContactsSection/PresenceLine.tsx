import { useTranslation } from 'react-i18next'

import { presenceLabel } from '@/lib/presence'

/** "у мережі" / "12 хв тому" under a contact's name. Renders nothing when the
 * contact is offline and hasn't shared their last-active time — an empty line
 * is better than telling the reader there is something they're not allowed to
 * see. */
export default function PresenceLine({
  online,
  lastSeenAt,
}: {
  online: boolean
  lastSeenAt: string | null | undefined
}) {
  const { t } = useTranslation()
  const label = presenceLabel({ online, lastSeenAt })

  if (label.kind === 'never') return null
  if (label.kind === 'online') {
    return (
      <span className="flex items-center gap-1 text-[11px] text-phosphor-soft">
        <span className="h-1.5 w-1.5 flex-none rounded-full bg-phosphor" />
        {t('presence.online')}
      </span>
    )
  }

  const text =
    label.kind === 'minutes'
      ? t('presence.minutesAgo', { count: label.value })
      : label.kind === 'hours'
        ? t('presence.hoursAgo', { count: label.value })
        : t('presence.daysAgo', { count: label.value })

  return <span className="text-[11px] text-slate-600">{text}</span>
}
